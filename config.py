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
neo4j_uri = os.getenv("NEO4J_URI")
logger.info(f"NEO4J_URI: {neo4j_uri}")

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
AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=proyectodawalessandro;AccountKey=slv70LImQP45UYRa/5qWmI2i8EVYBKhtg9mKAm7vrLNnD0glzQXcGueBwEZrtu9ay+5OIPh38r70+AStSAPV7A==;EndpointSuffix=core.windows.net"
AZURE_STORAGE_CONTAINER_NAME = "daw"

# Configuración de voz
VOICE_SIMILARITY_THRESHOLD = float(os.getenv("VOICE_SIMILARITY_THRESHOLD", "0.75"))

# Clave de API de GROQ
GROQ_API_KEY = "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"

# Credenciales de conexión a NEO4J - USANDO VALORES FIJOS DE AURA
NEO4J_URI = "neo4j+s://2908cbb6.databases.neo4j.io"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "okpcccPwFflZctGvH58eBUQ8Z7GM_XGtMCifFO6pgfg"

# Mostrar configuración
logger.info(f"Configuración final - NEO4J_URI: {NEO4J_URI}")