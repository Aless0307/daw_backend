import os
from dotenv import load_dotenv
import logging
import time
from keys import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

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
logger.info("Cargando configuración de Neo4j...")
NEO4J_MAX_RETRIES = int(os.getenv("NEO4J_MAX_RETRIES", "3"))
NEO4J_RETRY_DELAY = int(os.getenv("NEO4J_RETRY_DELAY", "2"))

# Configuración específica para Neo4j local
NEO4J_MAX_CONNECTION_LIFETIME = int(os.getenv("NEO4J_MAX_CONNECTION_LIFETIME", "3600"))  # 1 hora
NEO4J_MAX_CONNECTION_POOL_SIZE = int(os.getenv("NEO4J_MAX_CONNECTION_POOL_SIZE", "100"))
NEO4J_CONNECTION_TIMEOUT = int(os.getenv("NEO4J_CONNECTION_TIMEOUT", "10"))
NEO4J_KEEP_ALIVE = os.getenv("NEO4J_KEEP_ALIVE", "true").lower() == "true"

# Verificar variables de entorno críticas
if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    logger.error("Faltan variables de entorno críticas para Neo4j")
    raise ValueError("Las variables de entorno NEO4J_URI, NEO4J_USER y NEO4J_PASSWORD son requeridas")

logger.info(f"NEO4J_URI: {NEO4J_URI}")
logger.info("Variables de entorno de Neo4j cargadas correctamente")

# Configuración de JWT
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Configuración de Azure Storage
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

# Configuración de CORS
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8003",
    "https://daw-frontend.vercel.app"
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