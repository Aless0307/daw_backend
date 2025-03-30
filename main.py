# daw_backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auth import router as auth_router
from config import CORS_ORIGINS

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://daw-frontend.vercel.app", "https://vercel.live"],  # Orígenes específicos
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,  # Tiempo máximo de caché para las respuestas preflight
    supports_credentials=True  # Importante para cookies
)

# Incluir rutas de autenticación
app.include_router(auth_router, prefix="/auth", tags=["auth"])

@app.get("/")
async def root():
    return {"message": "API de autenticación con voz"}

