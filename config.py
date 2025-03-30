import os

# Configuración de URLs
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://daw-frontend.vercel.app")
PRODUCTION_URL = os.getenv("PRODUCTION_URL", "https://daw-frontend.vercel.app")

# Configuración de CORS
CORS_ORIGINS = [
    "https://daw-frontend.vercel.app",
    "https://vercel.live"
] 