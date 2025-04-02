import os
from dotenv import load_dotenv
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

# Verificar la carga de variables críticas
logger.info("Cargando configuración de Neo4j...")

# Configuración de Neo4j
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Verificar que las variables de entorno estén presentes
if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    logger.error("Faltan variables de entorno críticas para Neo4j")
    raise ValueError("Las variables de entorno NEO4J_URI, NEO4J_USER y NEO4J_PASSWORD son requeridas")

logger.info(f"NEO4J_URI: {NEO4J_URI}")
logger.info("Variables de entorno de Neo4j cargadas correctamente")

# Configuración de URLs
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://daw-frontend.vercel.app")
PRODUCTION_URL = os.getenv("PRODUCTION_URL", "https://daw-backend.onrender.com")

# Configuración de CORS
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8003",
    "https://daw-frontend.vercel.app"
]

# Configuración de JWT
SECRET_KEY = os.getenv("SECRET_KEY", "tu_clave_secreta_aqui")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Configuración de Azure
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "daw")

# Configuración de voz
VOICE_SIMILARITY_THRESHOLD = float(os.getenv("VOICE_SIMILARITY_THRESHOLD", "0.75"))

# Clave de API de GROQ
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Mostrar configuración final
logger.info("Configuración final cargada correctamente")