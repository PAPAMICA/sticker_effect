from flask import Flask, render_template, request, send_file, redirect, url_for
from PIL import Image, ImageOps, ImageFilter
import os
from io import BytesIO
from datetime import datetime
import uuid

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

def sticker_border_effect(image, border_size=10, size=(512, 512), smoothing=3, enable_shadow=True,
                     shadow_intensity=100, shadow_offset_x=0, shadow_offset_y=0, fill_holes=False):
    """Apply a sticker border effect to an image with advanced options"""
    # Open image
    img = Image.open(image).convert("RGBA")

    # Calculate final dimensions (fixed size)
    final_width, final_height = size

    # Calculate maximum available size for logo considering margins
    shadow_size = border_size // 2
    padding = max(abs(shadow_offset_x), abs(shadow_offset_y))
    total_margin = 2 * (border_size + shadow_size + padding)
    max_logo_width = final_width - total_margin
    max_logo_height = final_height - total_margin

    # Resize image preserving aspect ratio to fit available space
    img.thumbnail((max_logo_width, max_logo_height), Image.LANCZOS)

    # Add padding if needed (minimum 20px or border_size if larger)
    min_padding = max(20, border_size)
    img = add_padding_to_image(img, min_padding)

    # Create mask from alpha channel
    alpha = img.split()[3]

    if fill_holes:
        # Fill holes in the alpha channel using more aggressive morphological operations
        kernel_size = max(3, min(img.width // 20, img.height // 20))
        if kernel_size % 2 == 0:
            kernel_size += 1

        # Create a binary mask from alpha channel
        alpha_mask = alpha.point(lambda x: 255 if x > 128 else 0)
        
        # Apply closing operation (dilation followed by erosion)
        alpha_filled = alpha_mask.filter(ImageFilter.MaxFilter(kernel_size))
        alpha_filled = alpha_filled.filter(ImageFilter.MinFilter(kernel_size))
        
        # Apply opening operation (erosion followed by dilation) to clean up
        alpha_filled = alpha_filled.filter(ImageFilter.MinFilter(3))
        alpha_filled = alpha_filled.filter(ImageFilter.MaxFilter(3))
        
        # Create new image with filled alpha
        img_filled = Image.new("RGBA", img.size, (0, 0, 0, 0))
        r, g, b, _ = img.split()
        img_filled = Image.merge("RGBA", (r, g, b, alpha_filled))
        img = img_filled
        alpha = alpha_filled

    # Create and smooth mask for white border
    white_border = alpha.copy()
    # Apply MaxFilter multiple times with decreasing size for smoothing
    filter_size = border_size + (1 - border_size % 2)
    for i in range(smoothing + 1):
        current_size = max(3, filter_size - (i * 2))
        if current_size % 2 == 0:
            current_size += 1
        white_border = white_border.filter(ImageFilter.MaxFilter(current_size))

    # Create shadow mask if enabled
    if enable_shadow:
        shadow = white_border.copy()
        # Apply gaussian blur to soften shadow
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=border_size / 2))

    # Create final image with specified fixed size
    result = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))

    # Calculate center position for logo
    center_x = (final_width - img.width) // 2
    center_y = (final_height - img.height) // 2
    paste_position = (center_x, center_y)

    # Apply shadow if enabled
    if enable_shadow:
        shadow_layer = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
        shadow_position = (
            center_x + shadow_offset_x,
            center_y + shadow_offset_y
        )
        shadow_layer.paste((0, 0, 0, shadow_intensity), shadow_position, shadow)
        result = Image.alpha_composite(result, shadow_layer)

    # Apply white border
    white_layer = Image.new("RGBA", (final_width, final_height), (255, 255, 255, 255))
    white_layer.putalpha(Image.new("L", (final_width, final_height), 0))
    white_layer.paste((255, 255, 255, 255), paste_position, white_border)
    result = Image.alpha_composite(result, white_layer)

    # Apply original image
    img_layer = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
    img_layer.paste(img, paste_position, img)
    result = Image.alpha_composite(result, img_layer)

    return result

@app.route("/")
def upload():
    views = increment_views()
    return render_template("app.html", views=views)

@app.route("/process", methods=["POST"])
def process():
    border_size = int(request.form.get("border_size", 10))
    max_size = int(request.form.get("size", 512))
    smoothing = int(request.form.get("smoothing", 3))
    enable_shadow = request.form.get("enable_shadow") == "on"
    shadow_intensity = int(request.form.get("shadow_intensity", 100))
    shadow_offset_x = int(request.form.get("shadow_offset_x", 0))
    shadow_offset_y = int(request.form.get("shadow_offset_y", 0))
    fill_holes = request.form.get("fill_holes") == "on"

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
            size=(max_size, max_size),
            smoothing=smoothing,
            enable_shadow=enable_shadow,
            shadow_intensity=shadow_intensity,
            shadow_offset_x=shadow_offset_x,
            shadow_offset_y=shadow_offset_y,
            fill_holes=fill_holes
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
