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
from azure_storage import get_azure_status, verify_azure_storage, reset_connection

# Configurar logger
logger = logging.getLogger(__name__)

# Configurar logging
logging.basicConfig(
    level=logging.INFO if IS_PRODUCTION else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

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
    try:
        # Intentar comprobar servicios básicos sin fallar
        try:
            azure_status = get_azure_status()
        except Exception as e:
            logger.warning(f"Error al verificar Azure Storage en healthcheck: {str(e)}")
            azure_status = {"error": str(e)}
            
        services_status = {
            "azure_storage": azure_status,
            "groq_api": {"available": bool(GROQ_API_KEY)}
        }
        
        return {
            "status": "healthy",
            "environment": ENVIRONMENT,
            "timestamp": time.time(),
            "services": services_status
        }
    except Exception as e:
        # En caso de cualquier error, aún retornamos 200 OK
        logger.error(f"Error en healthcheck: {str(e)}")
        return {
            "status": "healthy",  # Decimos que es healthy para que Railway no reinicie
            "warning": "Servicio parcialmente disponible",
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
        "is_production": IS_PRODUCTION,
        "services": {
            "azure_storage": get_azure_status(),
            "groq_api": {"available": bool(GROQ_API_KEY)}
        }
    }

# Middleware para medir tiempo de procesamiento y logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Obtener detalles de la solicitud
    path = request.url.path
    method = request.method
    logger.info(f"📥 {method} {path}")
    
    # Establecer timeout más largo para rutas relacionadas con voz
    timeout = 60  # Default 60 segundos
    if '/voice/' in path or '/login-voice' in path:
        timeout = 120  # 2 minutos para rutas de voz
        logger.info(f"⏱️ Timeout extendido a {timeout}s para ruta de voz")
    
    try:
        # Procesar la solicitud con timeout
        import asyncio
        
        # Crear una tarea para procesar la solicitud
        async def process_request():
            return await call_next(request)
        
        # Ejecutar con timeout
        try:
            response = await asyncio.wait_for(process_request(), timeout=timeout)
            
            # Calcular tiempo de procesamiento
            process_time = time.time() - start_time
            logger.info(f"✅ {method} {path} completado en {process_time:.2f}s - Status: {response.status_code}")
            
            return response
        except asyncio.TimeoutError:
            # Si el procesamiento toma demasiado tiempo
            process_time = time.time() - start_time
            logger.error(f"⏱️ Timeout en {method} {path} después de {process_time:.2f}s")
            
            # Respuesta especial para timeout
            return JSONResponse(
                status_code=504,
                content={
                    "detail": "La solicitud tardó demasiado en procesarse. Por favor, intente más tarde."
                }
            )
            
    except Exception as e:
        # Para otras excepciones
        process_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"❌ Error en {method} {path}: {error_msg}")
        
        # Verificar si es un error relacionado con Azure Storage
        if "azure_storage" in error_msg.lower() or "container_client" in error_msg.lower():
            logger.error("⚠️ Error relacionado con Azure Storage - Verificando estado...")
            
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "El servicio de almacenamiento en la nube está temporalmente no disponible. Por favor, intente más tarde."
                }
            )
            
        # Error genérico para otras excepciones
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Se produjo un error en el servidor. Por favor, intente más tarde."
            }
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

# Ruta para reiniciar la conexión a Azure Storage
@app.post("/admin/reset-azure")
async def reset_azure():
    """Reinicia la conexión a Azure Storage"""
    reset_connection()
    return {
        "message": "Conexión a Azure Storage reiniciada correctamente"
    }

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

