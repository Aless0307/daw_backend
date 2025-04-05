# daw_backend/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import logging
import os
from config import (
    ALLOWED_ORIGINS,
    PRODUCTION_URL,
    GROQ_API_KEY,
    REQUEST_TIMEOUT,
    ENVIRONMENT,
    IS_PRODUCTION,
    CORS_CONFIG,
    PORT
)
from auth import router as auth_router
from voice_processing import router as voice_router
from groq import router as groq_router

# Configurar logging
logging.basicConfig(
    level=logging.INFO if IS_PRODUCTION else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Log del entorno actual
logger.info(f"Iniciando aplicación en entorno: {ENVIRONMENT}")
logger.info(f"Puerto configurado: {PORT}")

app = FastAPI(
    title="DAW Backend API",
    description="API para el proyecto DAW",
    version="1.0.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    **CORS_CONFIG
)

@app.get("/health")
async def health_check():
    """
    Ruta de healthcheck para Railway
    """
    return {
        "status": "healthy",
        "environment": ENVIRONMENT,
        "timestamp": time.time()
    }

@app.get("/")
async def root():
    """
    Ruta principal que también sirve como healthcheck
    """
    return {
        "status": "healthy",
        "message": "API de DAW funcionando correctamente",
        "environment": ENVIRONMENT,
        "is_production": IS_PRODUCTION
    }

# Middleware para medir tiempo de procesamiento y logging
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    
    # Log de la solicitud entrante
    logger.info(f"Solicitud recibida: {request.method} {request.url}")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log de la respuesta
        logger.info(f"Respuesta enviada: {response.status_code} en {process_time:.2f}s")
        
        return response
    except Exception as e:
        logger.error(f"Error procesando la solicitud: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"}
        )

# Incluir routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(voice_router, prefix="/voice", tags=["voice"])
app.include_router(groq_router, prefix="/groq", tags=["groq"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=not IS_PRODUCTION,
        workers=1,
        timeout_keep_alive=75
    )

