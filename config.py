# Configuración de URLs
FRONTEND_URL = "http://localhost:5173"  # URL local
PRODUCTION_URL = "https://daw-frontend.vercel.app"  # URL de producción

# Configuración de CORS
CORS_ORIGINS = [
    FRONTEND_URL,
    PRODUCTION_URL,
    "https://vercel.live",  # Para el feedback de Vercel
] 