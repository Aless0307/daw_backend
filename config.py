import os
from dotenv import load_dotenv
import logging

# Cargar variables de entorno
load_dotenv()

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
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
    "http://localhost:5173",
    "https://vercel.live",
    "https://*.vercel.live",
    "https://*.vercel.app"
]

# Configuración de URLs
PRODUCTION_URL = os.getenv("PRODUCTION_URL", "https://daw-backend.onrender.com")

# Clave de API de GROQ
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Configuración de timeouts
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

logger.info("Configuración final cargada correctamente")