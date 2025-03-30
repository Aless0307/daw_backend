import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de URLs
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://daw-frontend.vercel.app")
PRODUCTION_URL = os.getenv("PRODUCTION_URL", "https://daw-backend.onrender.com")

# Configuración de CORS
CORS_ORIGINS = [
    "http://localhost:5173",
    "https://daw-frontend.vercel.app"
]

# Configuración de JWT
SECRET_KEY = os.getenv("SECRET_KEY", "tu_clave_secreta_aqui")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Configuración de Azure
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "voice-recordings")

# Configuración de voz
VOICE_SIMILARITY_THRESHOLD = float(os.getenv("VOICE_SIMILARITY_THRESHOLD", "0.75"))

# Clave de API de GROQ
GROQ_API_KEY = "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"

# Credenciales de conexión a NEO4J
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "tu_contraseña")

# keys.py
SECRET_KEY = "4fa2cc1e198e12cd3872b1c94ddcf8b82938f5748c894fb60de73ad7f80385af"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# azure
         # <-- pon el nombre real de tu contenedor