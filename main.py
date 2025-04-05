# daw_backend/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import logging
from config import (
    ALLOWED_ORIGINS,
    PRODUCTION_URL,
    GROQ_API_KEY,
    REQUEST_TIMEOUT,
    ENVIRONMENT,
    IS_PRODUCTION,
    CORS_CONFIG
)
from auth import router as auth_router
from voice_processing import router as voice_router
from groq import router as groq_router
import os

# Configurar logging
logging.basicConfig(
    level=logging.INFO if IS_PRODUCTION else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('main.log')
    ]
)
logger = logging.getLogger(__name__)

# Log del entorno actual
logger.info(f"Iniciando aplicación en entorno: {ENVIRONMENT}")
logger.info(f"CORS permitidos: {ALLOWED_ORIGINS}")

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    **CORS_CONFIG
)

# Middleware para medir tiempo de procesamiento y logging
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    
    # Log de la solicitud entrante
    logger.info(f"Solicitud recibida: {request.method} {request.url}")
    logger.debug(f"Headers de la solicitud: {request.headers}")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log de la respuesta
        logger.info(f"Respuesta enviada: {response.status_code}")
        logger.debug(f"Tiempo de proceso: {process_time:.2f}s")
        
        return response
    except Exception as e:
        logger.error(f"Error procesando la solicitud: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"}
        )

@app.get("/")
async def root():
    return {
        "message": "API de DAW funcionando correctamente",
        "environment": ENVIRONMENT,
        "is_production": IS_PRODUCTION
    }

# Incluir routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(voice_router, prefix="/voice", tags=["voice"])
app.include_router(groq_router, prefix="/groq", tags=["groq"])

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=not IS_PRODUCTION)

