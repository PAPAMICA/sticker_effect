FROM python:3.14-slim

WORKDIR /app

# Copie des fichiers de l'application
COPY app/ .
COPY requirements.txt .

# Installation des dépendances Python (wheels binaires, pas de compilateur)
RUN pip install --no-cache-dir -r requirements.txt

# Exposition du port
EXPOSE 5000

# Commande pour démarrer l'application
CMD ["python", "app.py"]
