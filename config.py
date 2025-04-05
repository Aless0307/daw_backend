import os
from dotenv import load_dotenv
import logging

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

# Configuración de JWT
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Configuración de voz
VOICE_SIMILARITY_THRESHOLD = 0.85

# Configuración de Azure Storage
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = "daw"

# Configuración de CORS
ALLOWED_ORIGINS = [
    "https://daw-frontend.vercel.app",
    "https://dawbackend-production.up.railway.app",
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

# Configuración de URLs
PRODUCTION_URL = os.getenv("PRODUCTION_URL", "https://dawbackend-production.up.railway.app")

# Clave de API de GROQ
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Configuración de timeouts
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

logger.info("Configuración final cargada correctamente")