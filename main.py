# daw_backend/main.py
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import time
from auth import router as auth_router
from config import (
    CORS_ORIGINS, FRONTEND_URL, REQUEST_TIMEOUT,
    NEO4J_TIMEOUT, MAX_RETRIES, RETRY_DELAY
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware para logging y manejo de errores
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    client_host = request.client.host if request.client else "unknown"
    
    try:
        logger.info(f"Solicitud recibida: {request.method} {request.url.path} - Cliente: {client_host}")
        
        # Verificar timeout
        if time.time() - start_time > REQUEST_TIMEOUT:
            logger.error(f"Timeout en la solicitud: {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={"detail": "La solicitud ha excedido el tiempo de espera"}
            )
        
        response = await call_next(request)
        
        # Añadir headers CORS a la respuesta
        response.headers["Access-Control-Allow-Origin"] = FRONTEND_URL
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        
        process_time = time.time() - start_time
        logger.info(f"Solicitud completada: {request.method} {request.url.path} - Tiempo: {process_time:.2f}s")
        
        return response
        
    except Exception as e:
        logger.error(f"Error en la solicitud {request.url.path}: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Error interno del servidor"}
        )

# Manejador de errores global
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Error no manejado en {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Error interno del servidor"}
    )

# Incluir rutas de autenticación
app.include_router(auth_router, prefix="/auth", tags=["auth"])

@app.get("/")
async def root():
    """Endpoint de prueba para verificar que el servidor está funcionando"""
    return {"status": "ok", "message": "Servidor funcionando correctamente"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Iniciando servidor...")
    uvicorn.run(app, host="0.0.0.0", port=8003)

