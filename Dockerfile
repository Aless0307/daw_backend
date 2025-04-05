# Usa la imagen oficial de Python como base
FROM python:3.9-slim

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Establece variables de entorno
ENV PYTHONUNBUFFERED=1
ENV RAILWAY_ENVIRONMENT=production
ENV PORT=8000

# Instala las dependencias del sistema necesarias
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia el archivo de requerimientos
COPY requirements.txt .

# Instala las dependencias del backend
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código fuente al contenedor
COPY . .

# Expone el puerto
EXPOSE ${PORT}

# Script de inicio
RUN echo '#!/bin/bash\n\
uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 75' > /app/start.sh && \
    chmod +x /app/start.sh

# Configura el comando de inicio
CMD ["/app/start.sh"]
