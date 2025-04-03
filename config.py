import os
from dotenv import load_dotenv
import logging
import time
from typing import Optional
from keys import (
    NEO4J_URI_LOCAL,
    NEO4J_URI_PRODUCTION,
    NEO4J_USER,
    NEO4J_PASSWORD,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('config.log')
    ]
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

# Configuración de Neo4j
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
NEO4J_URI = NEO4J_URI_PRODUCTION if ENVIRONMENT == "production" else NEO4J_URI_LOCAL

# Configuración de Neo4j
logger.info("Cargando configuración de Neo4j...")
NEO4J_MAX_RETRIES = 3
NEO4J_RETRY_DELAY = 2  # segundos

# Configuración de Neo4j Aura
NEO4J_MAX_CONNECTION_LIFETIME = 300  # 5 minutos
NEO4J_MAX_CONNECTION_POOL_SIZE = 50
NEO4J_CONNECTION_TIMEOUT = 5
NEO4J_KEEP_ALIVE = True

# Verificar variables críticas
if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    logger.error("Faltan variables de entorno críticas para Neo4j")
    raise ValueError("Faltan variables de entorno críticas para Neo4j")

logger.info(f"Cargando configuración para entorno: {ENVIRONMENT}")
logger.info(f"URI de Neo4j: {NEO4J_URI}")

# Configuración de JWT
SECRET_KEY = SECRET_KEY
ALGORITHM = ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_MINUTES

# Configuración de Azure Storage
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

# Configuración de CORS
ALLOWED_ORIGINS = [
    "https://daw-frontend.vercel.app",
    "http://localhost:5173"
]

# URL del frontend
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://daw-frontend.vercel.app")

# Umbral de similitud de voz
VOICE_SIMILARITY_THRESHOLD = float(os.getenv("VOICE_SIMILARITY_THRESHOLD", "0.85"))

# Configuración de URLs
PRODUCTION_URL = os.getenv("PRODUCTION_URL", "https://daw-backend.onrender.com")

# Clave de API de GROQ
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Configuración de timeouts
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
NEO4J_TIMEOUT = int(os.getenv("NEO4J_TIMEOUT", "10"))

# Configuración de reintentos
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "2"))

# Mostrar configuración final
logger.info("Configuración final cargada correctamente")