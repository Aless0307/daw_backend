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
    IS_PRODUCTION
)
from auth import router as auth_router
from voice_processing import router as voice_router
from groq import router as groq_router

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

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware para medir tiempo de procesamiento
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

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
    logger.info("Iniciando servidor...")
    uvicorn.run(app, host="0.0.0.0", port=8003)

