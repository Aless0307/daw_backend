# daw_backend/main.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import logging
import os
import sys
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
# --- IMPORTACIONES DE ROUTERS ---
from auth import router as auth_router
from voice_processing import router as voice_router
from groq_utils import router as groq_router
from routes import accessibility
from routers import logic # <--- AÑADIR ESTA IMPORTACIÓN

# Importaciones que podrían estar faltando (si no están ya)
try:
    from azure_storage import get_azure_status, verify_azure_storage, reset_connection
except ImportError:
    # Manejar si el módulo no existe o no se necesita
    def get_azure_status(): return "not configured"
    def verify_azure_storage(): return False
    def reset_connection(): pass
    logging.warning("Módulo azure_storage no encontrado, usando funciones dummy.")

try:
    from insightface.app import FaceAnalysis # Asegúrate que esta importación sea necesaria y correcta
except ImportError:
     logging.warning("Módulo insightface.app no encontrado.")
     FaceAnalysis = None # Definir como None si no se encuentra

# --- FIN IMPORTACIONES ---

# Configurar logger (tu código existente)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[ logging.StreamHandler(stream=sys.stdout) ]
)
for noisy_logger in ['numba', 'numba.core', 'numba.core.byteflow', 'matplotlib', 'PIL']:
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)
logger = logging.getLogger("main")
logger.setLevel(logging.INFO)
logger.error("=" * 50)
logger.error(f"INICIANDO APLICACIÓN EN {ENVIRONMENT}") # Mensaje ajustado
# ... (otros logs de inicio) ...
logger.error("=" * 50)


app = FastAPI(
    title="DAW Backend API",
    description="API para el proyecto DAW",
    version="1.0.0"
)

# Configurar CORS (tu código existente)
app.add_middleware(
    CORSMiddleware,
    **CORS_CONFIG
)

# Middleware para medir tiempo (tu código existente)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    path = request.url.path
    method = request.method
    logger.info(f"📥 {method} {path}")
    timeout = 60
    if '/voice/' in path or '/login-voice' in path:
        timeout = 240
        logger.info(f"⏱️ Timeout extendido a {timeout}s para ruta de voz")
    try:
        import asyncio
        async def process_request(): return await call_next(request)
        response = await asyncio.wait_for(process_request(), timeout=timeout)
        process_time = time.time() - start_time
        logger.info(f"✅ {method} {path} completado en {process_time:.2f}s - Status: {response.status_code}")
        return response
    except asyncio.TimeoutError:
        process_time = time.time() - start_time
        logger.error(f"⏱️ Timeout en {method} {path} después de {process_time:.2f}s")
        return JSONResponse(status_code=504, content={"detail": "Timeout procesando la solicitud."})
    except Exception as e:
        process_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"❌ Error en {method} {path}: {error_msg}", exc_info=True) # Añadir exc_info para más detalle
        # ... (manejo de error Azure existente) ...
        return JSONResponse(status_code=500, content={"detail": "Error interno del servidor."})


# --- Rutas Principales y de Salud ---
@app.get("/health")
async def health_check():
    return {"status": "healthy", "environment": ENVIRONMENT, "timestamp": time.time()}

@app.get("/")
async def root():
    return {"status": "healthy", "message": "API de DAW funcionando", "environment": ENVIRONMENT}

@app.get("/status")
async def check_status():
    return {"status": "online", "azure_storage": get_azure_status()}

# --- Incluir Routers ---
app.include_router(auth_router, prefix="/auth", tags=["Authentication"]) # OK
app.include_router(voice_router, prefix="/voice", tags=["Voice Processing"]) # OK
app.include_router(groq_router, prefix="/groq", tags=["Groq AI"]) # OK
app.include_router(accessibility.router, prefix="/api", tags=["Accessibility"]) # OK - ¿Prefijo correcto?

# --- ¡¡AÑADIR ESTA LÍNEA!! ---
# Incluye las rutas de routers/logic.py bajo /auth/api
app.include_router(logic.router, prefix="/auth/api", tags=["Logic Problems"])
# --- FIN LÍNEA A AÑADIR ---


# --- Rutas Administrativas (Opcional) ---
@app.post("/admin/reconnect-azure")
async def reconnect_azure():
    success = verify_azure_storage()
    status = get_azure_status()
    if success: return {"message": "Conexión Azure OK", "status": status}
    else: return JSONResponse(status_code=503, content={"message": "Fallo conexión Azure", "status": status})

@app.post("/admin/reset-azure")
async def reset_azure():
    reset_connection()
    return {"message": "Conexión Azure reiniciada"}

# --- Ejecutar Servidor (tu código existente) ---
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