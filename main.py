# daw_backend/main.py
from fastapi import FastAPI, HTTPException, Depends, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import status
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
import jwt
import os
import json
import azure.storage.blob
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError
import uuid
import logging
import time
from config import (
    SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES,
    AZURE_STORAGE_CONNECTION_STRING, AZURE_STORAGE_CONTAINER_NAME,
    CORS_ORIGINS, FRONTEND_URL
)
from auth import router as auth_router

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

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8003", "https://daw-frontend.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Middleware para logging de solicitudes
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info(f"Solicitud recibida: {request.method} {request.url.path} - Cliente: {request.client.host}")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"Respuesta enviada: {request.method} {request.url.path} - Código: {response.status_code} - Tiempo: {process_time:.2f}s")
        return response
    except Exception as e:
        logger.error(f"Error al procesar solicitud: {request.method} {request.url.path} - Error: {str(e)}")
        raise

# Incluir rutas de autenticación
app.include_router(auth_router, prefix="/auth", tags=["auth"])

@app.get("/")
async def root():
    logger.info("Acceso a la ruta raíz")
    return {"message": "API de autenticación con voz"}

