FROM python:3.9-slim

WORKDIR /app

# Installation des dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copie des fichiers de l'application
COPY app/ .
COPY requirements.txt .

# Installation des dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Exposition du port
EXPOSE 5000

# Commande pour démarrer l'application
CMD ["python", "app.py"]