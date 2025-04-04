from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from datetime import timedelta
from typing import Optional, Dict
import logging
import hashlib
import os
from utils.auth_utils import create_access_token, get_current_user
from mongodb_client import MongoDBClient
from voice_processing import extract_embedding, compare_voices
from azure_storage import upload_voice_recording, download_voice_recording
from config import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, VOICE_SIMILARITY_THRESHOLD
from pydantic import BaseModel
import librosa
import numpy as np

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('auth.log')
    ]
)
logger = logging.getLogger(__name__)

router = APIRouter()
mongo_client = MongoDBClient()

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    email: str
    voice_url: Optional[str] = None

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    username: Optional[str] = None
    email: str
    voice_url: Optional[str] = None

@router.post("/register", response_model=LoginResponse)
async def register(
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    voice_recording: UploadFile = File(None)
):
    try:
        logger.info(f"Intento de registro para: {email}")

        # Verificar si el usuario ya existe
        existing_user = mongo_client.get_user_by_email(email)
        if existing_user:
            logger.warning(f"Intento de registro con email ya existente: {email}")
            raise HTTPException(status_code=400, detail="El email ya está registrado")

        # Procesar la grabación de voz si se proporciona
        voice_embedding = None
        voice_url = None
        if voice_recording:
            logger.info("Procesando grabación de voz")
            
            # Guardar archivo temporalmente
            temp_file = f"temp_{voice_recording.filename}"
            try:
                with open(temp_file, "wb") as buffer:
                    content = await voice_recording.read()
                    if not content:
                        raise HTTPException(status_code=400, detail="El archivo de voz está vacío")
                    buffer.write(content)
                    logger.info(f"Archivo de voz guardado temporalmente: {temp_file}")

                # Extraer embedding
                voice_embedding = extract_embedding(temp_file)
                if voice_embedding is None:
                    raise HTTPException(status_code=400, detail="No se pudo extraer el embedding de la voz")

                # Subir a Azure Storage
                voice_url = await upload_voice_recording(temp_file, email)
                logger.info(f"Archivo subido a Azure. URL: {voice_url}")

            finally:
                # Limpiar archivo temporal
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.info("Archivo temporal eliminado")

        # Crear usuario
        logger.info("Creando usuario en MongoDB")
        success = mongo_client.create_user(
            username=username,
            email=email,
            password=password,
            voice_embedding=voice_embedding,
            voice_url=voice_url
        )

        if success:
            logger.info(f"Usuario registrado exitosamente: {email}")
            # Crear token de acceso
            access_token = create_access_token(data={"sub": email})
            return LoginResponse(
                access_token=access_token,
                token_type="bearer",
                username=username,
                email=email,
                voice_url=voice_url
            )
        else:
            logger.error(f"Error al crear usuario en la base de datos: {email}")
            raise HTTPException(status_code=500, detail="Error al crear el usuario")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al registrar usuario: {str(e)}")
        raise HTTPException(status_code=500, detail="Error en el servidor")

@router.post("/login", response_model=LoginResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Inicia sesión con credenciales (usuario y contraseña)
    """
    try:
        logger.info(f"Intento de inicio de sesión para: {form_data.username}")
        
        # Hashear la contraseña
        hashed_password = hashlib.sha256(form_data.password.encode()).hexdigest()
        
        # Verificar credenciales
        user = mongo_client.verify_user_credentials(form_data.username, hashed_password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Crear token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["email"]},
            expires_delta=access_token_expires
        )
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            username=user.get("username"),
            email=user["email"],
            voice_url=user.get("voice_url")
        )
        
    except Exception as e:
        logger.error(f"Error en el login: {str(e)}")
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en el login: {str(e)}"
        )

@router.post("/login-voice", response_model=LoginResponse)
async def login_with_voice(
    email: str = Form(...),
    voice_recording: UploadFile = File(...)
):
    temp_file = None
    original_voice_path = None
    
    try:
        logger.info(f"Iniciando login con voz para email: {email}")
        logger.info(f"Tamaño del archivo recibido: {voice_recording.size} bytes")
        logger.info(f"Tipo de contenido: {voice_recording.content_type}")
        
        # Buscar usuario por email
        user = mongo_client.get_user_by_email(email)
        if not user:
            logger.warning(f"Usuario no encontrado para el email: {email}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Usuario no encontrado"}
            )

        # Verificar que el usuario tenga un embedding de voz registrado
        if not user.get('voice_url'):
            logger.warning(f"Usuario {email} no tiene archivo de voz registrado")
            return JSONResponse(
                status_code=400,
                content={"detail": "No hay voz registrada para este usuario"}
            )

        # Descargar el archivo WAV original de Azure Storage
        original_voice_path = f"original_{user['voice_url'].split('/')[-1]}"
        
        try:
            # Descargar el archivo original
            await download_voice_recording(user['voice_url'], original_voice_path)
            logger.info(f"Archivo original descargado exitosamente: {original_voice_path}")

            # Guardar el archivo temporal de la nueva grabación
            temp_file = f"temp_{voice_recording.filename}"
            content = await voice_recording.read()
            
            if not content:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "El archivo de voz está vacío"}
                )
                
            with open(temp_file, "wb") as buffer:
                buffer.write(content)
                logger.info(f"Archivo de voz temporal guardado: {temp_file}")

            # Verificar calidad del audio
            y, sr = librosa.load(temp_file, sr=None)
            if len(y) == 0:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "El archivo de voz no contiene audio"}
                )
            
            # Calcular la energía del audio
            energy = np.sum(np.abs(y))
            if energy < 0.1:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "El audio es demasiado silencioso"}
                )

            # Extraer embeddings
            logger.info("Extrayendo embedding de la nueva grabación...")
            new_embedding = extract_embedding(temp_file)
            if new_embedding is None:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "No se pudo procesar la grabación de voz"}
                )

            logger.info("Extrayendo embedding de la grabación original...")
            original_embedding = extract_embedding(original_voice_path)
            if original_embedding is None:
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Error al procesar la voz registrada"}
                )

            # Comparar voces
            logger.info("Comparando embeddings de voz...")
            similarity = compare_voices(original_embedding, new_embedding)
            logger.info(f"Similitud calculada: {similarity}")

            if similarity < VOICE_SIMILARITY_THRESHOLD:
                return JSONResponse(
                    status_code=401,
                    content={"detail": f"La voz no coincide (similitud: {similarity:.2f})"}
                )

            # Generar token
            logger.info("Generando token de acceso...")
            access_token = create_access_token(
                data={"sub": user["email"]},
                expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            )

            return LoginResponse(
                access_token=access_token,
                token_type="bearer",
                username=user.get("username"),
                email=user["email"],
                voice_url=user.get("voice_url")
            )

        except Exception as e:
            logger.error(f"Error procesando la voz: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"detail": f"Error procesando la voz: {str(e)}"}
            )

    except Exception as e:
        logger.error(f"Error en login con voz: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Error en el servidor: {str(e)}"}
        )
        
    finally:
        # Limpiar archivos temporales
        logger.info("Limpiando archivos temporales...")
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)
        if original_voice_path and os.path.exists(original_voice_path):
            os.remove(original_voice_path)

@router.get("/me", response_model=LoginResponse)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return LoginResponse(
        access_token="",  # No es necesario devolver el token aquí
        token_type="bearer",
        username=current_user.get("username"),
        email=current_user["email"],
        voice_url=current_user.get("voice_url")
    ) 