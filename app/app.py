from flask import Flask, render_template, request, send_file, redirect, url_for
from PIL import Image, ImageOps, ImageFilter, ImageDraw
import os
from io import BytesIO
from datetime import datetime
import uuid
import numpy as np
from scipy import ndimage

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
PROCESSED_FOLDER = "processed"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# File to store view count
VIEWS_FILE = "views.txt"

def get_views():
    """Get the number of views"""
    try:
        with open(VIEWS_FILE, 'r') as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0

def increment_views():
    """Increment the view counter"""
    views = get_views()
    views += 1
    with open(VIEWS_FILE, 'w') as f:
        f.write(str(views))
    return views

def generate_unique_filename(original_filename):
    """Generate a unique filename while keeping the original name"""
    name, ext = os.path.splitext(original_filename)
    unique_id = str(uuid.uuid4())[:3]
    return f"{name}_{unique_id}.png"  # Force .png extension

def add_padding_to_image(img, min_padding=20):
    """Add padding around the image if needed"""
    # Find non-transparent boundaries of the image
    bbox = img.getbbox()
    if not bbox:
        return img

    # Check if image touches borders
    left_space = bbox[0]
    top_space = bbox[1]
    right_space = img.width - bbox[2]
    bottom_space = img.height - bbox[3]

    # Calculate needed padding
    padding_left = max(0, min_padding - left_space)
    padding_top = max(0, min_padding - top_space)
    padding_right = max(0, min_padding - right_space)
    padding_bottom = max(0, min_padding - bottom_space)

    # If no padding needed, return original image
    if padding_left == padding_right == padding_top == padding_bottom == 0:
        return img

    # Create new image with padding
    new_width = img.width + padding_left + padding_right
    new_height = img.height + padding_top + padding_bottom
    padded_img = Image.new("RGBA", (new_width, new_height), (0, 0, 0, 0))
    padded_img.paste(img, (padding_left, padding_top))

    return padded_img

def create_peeled_corner(size, corner_size=50, color=(200, 200, 200, 255)):
    """Create a peeled corner effect"""
    # Create image for peeled corner
    corner = Image.new('RGBA', (corner_size * 2, corner_size * 2), (0, 0, 0, 0))

    # Draw the peeled corner (triangle)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(corner)
    draw.polygon([(corner_size * 2, 0), (corner_size * 2, corner_size * 2), (0, corner_size * 2)],
                fill=color)

    # Add light shadow
    shadow = Image.new('RGBA', corner.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.polygon([(corner_size * 2, 0), (corner_size * 2, corner_size * 2), (0, corner_size * 2)],
                       fill=(0, 0, 0, 50))

    # Offset shadow slightly
    corner_with_shadow = Image.new('RGBA', corner.size, (0, 0, 0, 0))
    corner_with_shadow.paste(shadow, (5, 5))
    corner_with_shadow.paste(corner, (0, 0), corner)

    return corner_with_shadow

def hex_to_rgba(hex_color):
    """Convert hex color to RGBA tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4)) + (255,)

def fill_interior_holes(alpha, color):
    """Fill interior holes with specified color"""
    # Convert alpha to numpy array
    alpha_np = np.array(alpha)

    # Create binary mask (0 for transparent, 1 for non-transparent)
    binary = alpha_np > 128

    # Create a mask for the exterior (flood fill from the borders)
    exterior_mask = np.zeros_like(binary, dtype=bool)
    exterior_mask[0, :] = ~binary[0, :]  # top edge
    exterior_mask[-1, :] = ~binary[-1, :]  # bottom edge
    exterior_mask[:, 0] = ~binary[:, 0]  # left edge
    exterior_mask[:, -1] = ~binary[:, -1]  # right edge

    # Flood fill from the borders to identify exterior transparent regions
    from scipy import ndimage
    structure = ndimage.generate_binary_structure(2, 2)  # 8-connectivity
    exterior_mask = ndimage.binary_dilation(exterior_mask, structure=structure, mask=~binary)
    while np.any(np.logical_and(~binary, ~exterior_mask)):
        new_exterior = ndimage.binary_dilation(exterior_mask, structure=structure, mask=~binary)
        if np.array_equal(new_exterior, exterior_mask):
            break
        exterior_mask = new_exterior

    # The holes are the transparent regions that are not part of the exterior
    holes = np.logical_and(~binary, ~exterior_mask)

    # Dilate the holes by 3 pixels
    holes = ndimage.binary_dilation(holes, iterations=10)

    # Create the output alpha channel
    result = alpha_np.copy()
    result[holes] = 255  # Fill holes with full opacity

    return Image.fromarray(result)

def sticker_border_effect(image, border_size=10, size=(512, 512), smoothing=3, enable_shadow=True,
                     shadow_intensity=100, shadow_offset_x=0, shadow_offset_y=0, fill_holes=True,
                     border_color="#FFFFFF", padding_size=20):
    """Apply a sticker border effect to an image with advanced options"""
    # Convert hex color to RGBA
    border_rgba = hex_to_rgba(border_color)

    # Open image
    img = Image.open(image).convert("RGBA")

    # Calculate final dimensions (fixed size)
    final_width, final_height = size

    # Calculate all margins needed
    border_margin = border_size * 2  # Double the border size for both sides
    shadow_margin = (max(abs(shadow_offset_x), abs(shadow_offset_y)) + border_size) * 2 if enable_shadow else 0
    padding_margin = padding_size * 2  # Double the padding for both sides
    
    # Total margin needed
    total_margin = border_margin + shadow_margin + padding_margin

    # Calculate maximum available size for logo
    max_logo_width = final_width - total_margin
    max_logo_height = final_height - total_margin

    # Resize image preserving aspect ratio to fit available space
    img.thumbnail((max_logo_width, max_logo_height), Image.LANCZOS)

    # Create a new image with padding
    padded_width = img.width + padding_margin + border_margin
    padded_height = img.height + padding_margin + border_margin
    padded_img = Image.new("RGBA", (padded_width, padded_height), (0, 0, 0, 0))
    
    # Calculate position to paste the original image (centered)
    paste_x = (padded_width - img.width) // 2
    paste_y = (padded_height - img.height) // 2
    padded_img.paste(img, (paste_x, paste_y))
    
    # Update img to use the padded version
    img = padded_img

    # Create mask from alpha channel
    alpha = img.split()[3]

    # Create and smooth mask for border
    border_mask = alpha.copy()
    # Apply MaxFilter multiple times with decreasing size for smoothing
    filter_size = border_size + (1 - border_size % 2)
    for i in range(smoothing + 1):
        current_size = max(3, filter_size - (i * 2))
        if current_size % 2 == 0:
            current_size += 1
        border_mask = border_mask.filter(ImageFilter.MaxFilter(current_size))

    # Create final image with specified fixed size
    result = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))

    # Calculate center position for the padded image
    center_x = (final_width - img.width) // 2
    center_y = (final_height - img.height) // 2
    paste_position = (center_x, center_y)

    # Apply colored border first
    border_layer = Image.new("RGBA", (final_width, final_height), border_rgba)
    border_layer.putalpha(Image.new("L", (final_width, final_height), 0))
    border_layer.paste(border_rgba, paste_position, border_mask)
    result = Image.alpha_composite(result, border_layer)

    # Apply original image
    img_layer = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
    img_layer.paste(img, paste_position)
    result = Image.alpha_composite(result, img_layer)

    if fill_holes:
        # Create a new alpha channel that includes the border
        combined_alpha = Image.new("L", img.size, 0)
        combined_alpha.paste(alpha, (0, 0))
        combined_alpha.paste(255, (0, 0), border_mask)

        # Fill interior holes considering both the image and border
        alpha_filled = fill_interior_holes(combined_alpha, border_rgba)

        # Create a mask for the holes only
        holes_mask_data = np.array(alpha_filled) - np.array(combined_alpha)
        # Binarize the mask - any positive difference becomes fully opaque
        holes_mask_data = (holes_mask_data > 0) * 255
        holes_mask = Image.fromarray(holes_mask_data.astype('uint8'))

        # Create a color layer for the holes
        holes_layer = Image.new("RGBA", img.size, border_rgba)
        holes_layer.putalpha(holes_mask)

        # Create holes layer at final size
        final_holes_layer = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
        final_holes_layer.paste(holes_layer, paste_position)

        # Composite the holes with the result
        result = Image.alpha_composite(result, final_holes_layer)

    # Apply shadow if enabled (last step)
    if enable_shadow:
        shadow = border_mask.copy()
        # Apply gaussian blur to soften shadow
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=border_size / 2))

        shadow_layer = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
        shadow_position = (
            center_x + shadow_offset_x,
            center_y + shadow_offset_y
        )
        shadow_layer.paste((0, 0, 0, shadow_intensity), shadow_position, shadow)

        # Create a new result image with shadow as background
        final_result = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
        final_result = Image.alpha_composite(final_result, shadow_layer)
        final_result = Image.alpha_composite(final_result, result)
        return final_result

    return result

@app.route("/")
def upload():
    views = increment_views()
    return render_template("app.html", views=views)

@app.route("/process", methods=["POST"])
def process():
    border_size = int(request.form.get("border_size", 10))
    size_option = request.form.get("size", "512")
    # Size options dictionary
    size_options = {
        "256": (256, 256),
        "512": (512, 512),
        "1024": (1024, 1024),
        "1536": (1536, 1536),
        "2048": (2048, 2048),
        "instagram_story": (1080, 1920),
        "instagram_post": (1080, 1080),
        "facebook_post": (1200, 630),
        "twitter_post": (1200, 675)
    }
    size = size_options.get(size_option, (512, 512))
    
    smoothing = int(request.form.get("smoothing", 3))
    enable_shadow = request.form.get("enable_shadow") == "on"
    shadow_intensity = int(request.form.get("shadow_intensity", 100))
    shadow_offset_x = int(request.form.get("shadow_offset_x", 0))
    shadow_offset_y = int(request.form.get("shadow_offset_y", 0))
    fill_holes = request.form.get("fill_holes") == "on"
    border_color = request.form.get("border_color", "#FFFFFF")
    padding_size = int(request.form.get("padding_size", 20))

    files = request.files.getlist("images")
    processed_files = []
    dimensions = {}

    for file in files:
        if file.filename == "":
            continue

        # Check file extension
        _, ext = os.path.splitext(file.filename)
        if ext.lower() not in ['.png']:
            continue

        # Generate unique filename
        new_name = generate_unique_filename(file.filename)
        output_path = os.path.join(PROCESSED_FOLDER, new_name)

        # Apply effect and save image
        processed_img = sticker_border_effect(
            file,
            border_size=border_size,
            size=size,
            smoothing=smoothing,
            enable_shadow=enable_shadow,
            shadow_intensity=shadow_intensity,
            shadow_offset_x=shadow_offset_x,
            shadow_offset_y=shadow_offset_y,
            fill_holes=fill_holes,
            border_color=border_color,
            padding_size=padding_size
        )
        processed_img.save(output_path, format="PNG")
        processed_files.append(output_path)
        dimensions[output_path] = processed_img.size

    return render_template("gallery.html", files=processed_files, dimensions=dimensions)

@app.route("/download/<path:filename>")
def download(filename):
    view = request.args.get('view', False)
    if view:
        return send_file(filename)
    return send_file(filename, as_attachment=True)

@app.route("/download_all", methods=["POST"])
def download_all():
    """Download specified images as ZIP"""
    try:
        files = request.json.get('files', [])
        if not files:
            return {"error": "No files specified"}, 400

        # Zip specified images
        import zipfile
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for file in files:
                if os.path.isfile(file):
                    zip_file.write(file, arcname=os.path.basename(file))

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='stickers.zip'
        )
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/delete/<path:filename>")
def delete_image(filename):
    """Delete a generated image"""
    try:
        os.remove(filename)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

@app.route("/clear_all")
def clear_all():
    """Delete all generated images"""
    try:
        for file in os.listdir(PROCESSED_FOLDER):
            file_path = os.path.join(PROCESSED_FOLDER, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)