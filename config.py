import os

# Configuración de URLs
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
PRODUCTION_URL = os.getenv("PRODUCTION_URL", "https://daw-frontend.vercel.app")

# Obtener CORS_ORIGINS de las variables de entorno o usar valores por defecto
CORS_ORIGINS_STR = os.getenv("CORS_ORIGINS", f"{FRONTEND_URL},{PRODUCTION_URL},https://vercel.live")
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_STR.split(",")] 