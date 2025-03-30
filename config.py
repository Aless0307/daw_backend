import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de URLs
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://daw-frontend.vercel.app")
PRODUCTION_URL = os.getenv("PRODUCTION_URL", "https://daw-frontend.vercel.app")

# Configuración de CORS
CORS_ORIGINS = [
    "https://daw-frontend.vercel.app",
    "https://vercel.live",
    "http://localhost:5173",
    "http://localhost:8003"
]

# Configuración de JWT
SECRET_KEY = os.getenv("SECRET_KEY", "tu_clave_secreta_aqui")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Configuración de Azure
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "voice-recordings") 