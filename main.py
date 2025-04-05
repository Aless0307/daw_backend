# daw_backend/main.py
from fastapi import FastAPI, Request, HTTPException
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
from azure_storage import get_azure_status, verify_azure_storage

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
    Ruta de healthcheck para Railway.
    Siempre devuelve 200 OK, pero incluye el estado de los servicios.
    """
    services_status = {
        "azure_storage": get_azure_status(),
        "groq_api": {"available": bool(GROQ_API_KEY)}
    }
    
    return {
        "status": "healthy",
        "environment": ENVIRONMENT,
        "timestamp": time.time(),
        "services": services_status
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
        "is_production": IS_PRODUCTION,
        "services": {
            "azure_storage": get_azure_status(),
            "groq_api": {"available": bool(GROQ_API_KEY)}
        }
    }

# Middleware para medir tiempo de procesamiento y logging
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    
    # Log de la solicitud entrante
    logger.info(f"📥 {request.method} {request.url.path}")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log de la respuesta con emojis según el código de estado
        status_emoji = "✅" if response.status_code < 400 else "❌"
        logger.info(f"{status_emoji} {response.status_code} - {request.method} {request.url.path} ({process_time:.2f}s)")
        
        return response
    except Exception as e:
        process_time = time.time() - start_time
        error_msg = str(e)
        
        # Errores específicos
        if "UnboundLocalError: local variable" in error_msg and "azure_storage" in error_msg:
            logger.error(f"❌ Error de Azure Storage: {error_msg}")
            return JSONResponse(
                status_code=503,
                content={"detail": "El servicio de autenticación por voz no está disponible temporalmente. Por favor, intente más tarde o use otro método de inicio de sesión."}
            )
            
        logger.error(f"❌ Error en {request.method} {request.url.path}: {error_msg}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"}
        )

# Incluir routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(voice_router, prefix="/voice", tags=["voice"])
app.include_router(groq_router, prefix="/groq", tags=["groq"])

# Ruta para verificar el estado de la API
@app.get("/status")
async def check_status():
    return {
        "status": "online",
        "azure_storage": get_azure_status()
    }

# Ruta para verificar y reintentar la conexión a Azure Storage
@app.post("/admin/reconnect-azure")
async def reconnect_azure():
    """Intenta reconectar a Azure Storage"""
    success = verify_azure_storage()
    status = get_azure_status()
    
    if success:
        return {
            "message": "Conexión a Azure Storage establecida correctamente",
            "status": status
        }
    else:
        return JSONResponse(
            status_code=503,
            content={
                "message": "No se pudo establecer conexión a Azure Storage",
                "status": status
            }
        )

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

