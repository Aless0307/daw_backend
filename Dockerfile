# Usa la imagen oficial de Python como base
FROM python:3.11-slim

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
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copia el archivo de requerimientos
COPY requirements.txt .

# Instala las dependencias del backend
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código fuente al contenedor
COPY . .

# Crea directorios para archivos temporales
RUN mkdir -p /app/temp_files && chmod 777 /app/temp_files

# Script de inicio mejorado
RUN echo '#!/bin/bash\n\
echo "Starting server..."\n\
echo "Railway environment: $RAILWAY_ENVIRONMENT"\n\
echo "Current directory: $PWD"\n\
echo "Files in directory:"\n\
ls -la\n\
python -m uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 300 --log-level debug\n\
' > /app/start.sh && chmod +x /app/start.sh

# Expone el puerto
EXPOSE ${PORT}

# Configura el comando de inicio
CMD ["/app/start.sh"]
