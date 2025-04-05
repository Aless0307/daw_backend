import os
from dotenv import load_dotenv
import logging
import secrets
from datetime import timedelta

# Cargar variables de entorno
load_dotenv()

# Detección del entorno
def get_environment():
    """
    Detecta el entorno actual de la aplicación.
    Returns:
        str: 'production' si está en Railway, 'development' si está en local
    """
    railway_env = os.getenv("RAILWAY_ENVIRONMENT")
    if railway_env == "production":
        return "production"
    return "development"

# Detección del entorno
ENVIRONMENT = get_environment()
IS_PRODUCTION = ENVIRONMENT == "production"

# Generar SECRET_KEY si no existe
def generate_secret_key():
    """Genera una clave secreta segura"""
    return secrets.token_hex(32)

# Configuración de JWT
SECRET_KEY = os.getenv("SECRET_KEY", generate_secret_key())
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Configuración de voz
VOICE_SIMILARITY_THRESHOLD = float(os.getenv("VOICE_SIMILARITY_THRESHOLD", "0.85"))

# Configuración de Azure Storage para desarrollo local
LOCAL_AZURE_CONNECTION = "DefaultEndpointsProtocol=https;AccountName=proyectodawalessandro;AccountKey=tu_key_aqui;EndpointSuffix=core.windows.net"

# Configuración de Azure Storage
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", LOCAL_AZURE_CONNECTION)
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME", "daw")

# Configuración de URLs
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://daw-frontend.vercel.app")
PRODUCTION_URL = os.getenv("PRODUCTION_URL", "https://dawbackend-production.up.railway.app")

# Configuración de CORS
ALLOWED_ORIGINS = [
    FRONTEND_URL,
    PRODUCTION_URL,
    "http://localhost:5173",
    "http://localhost:8000",
    "http://localhost:8003"
] if IS_PRODUCTION else [
    "http://localhost:5173",
    "http://localhost:8000",
    "http://localhost:8003"
]

# Configuración adicional de CORS
CORS_CONFIG = {
    "allow_origins": ALLOWED_ORIGINS,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

# Clave de API de GROQ - Usar una clave de prueba para desarrollo
DEFAULT_GROQ_KEY = "gsk_your_default_key" if not IS_PRODUCTION else None
GROQ_API_KEY = os.getenv("GROQ_API_KEY", DEFAULT_GROQ_KEY)

# Configuración de timeouts
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

# Configuración de logging
logging.basicConfig(
    level=logging.INFO if IS_PRODUCTION else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('config.log')
    ]
)
logger = logging.getLogger(__name__)

# Log de configuración
logger.info(f"Entorno: {ENVIRONMENT}")
logger.info(f"Frontend URL: {FRONTEND_URL}")
logger.info(f"Production URL: {PRODUCTION_URL}")
logger.info(f"CORS permitidos: {ALLOWED_ORIGINS}")

# Validación de configuración crítica en producción
if IS_PRODUCTION:
    if not AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_CONNECTION_STRING == LOCAL_AZURE_CONNECTION:
        logger.warning("⚠️ Usando conexión local de Azure Storage en producción")
    
    if not GROQ_API_KEY or GROQ_API_KEY == DEFAULT_GROQ_KEY:
        logger.warning("⚠️ Usando clave de GROQ por defecto en producción")
else:
    logger.info("Ejecutando en modo desarrollo con configuración por defecto")

logger.info("Configuración final cargada correctamente")