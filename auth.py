from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import jwt
import os
import tempfile
import time
import logging
import hashlib
import numpy as np
import io
from neo4j_client import Neo4jClient
from config import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, VOICE_SIMILARITY_THRESHOLD
from voice_processing import extract_voice_embedding, compare_voice_embeddings
from azure_storage import upload_voice_recording

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
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Modelos
class Token(BaseModel):
    access_token: str
    token_type: str
    username: str
    email: str

class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    password: str

class UserInDB(UserBase):
    hashed_password: str

# Inicializar cliente Neo4j
neo4j_client = Neo4jClient()

# Funciones de autenticación
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    logger.info(f"Creando token de acceso para: {data.get('sub', 'desconocido')}")
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
    logger.debug(f"Token creado con expiración: {expire}")
    return encoded_jwt

def get_password_hash(password: str) -> str:
    logger.debug("Generando hash de contraseña")
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    logger.debug("Verificando contraseña")
    return get_password_hash(plain_password) == hashed_password

@router.post("/register", response_model=Dict[str, str])
async def register(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    voice: Optional[UploadFile] = File(None)
):
    logger.info(f"Iniciando registro de usuario: {username} ({email})")
    start_time = time.time()
    
    try:
        # Verificar si el usuario ya existe
        existing_user = neo4j_client.get_user_by_email(email)
        if existing_user:
            logger.warning(f"Intento de registro con email existente: {email}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "El email ya está registrado"}
            )
        
        # Procesar voz si se proporciona
        voice_embedding = None
        voice_url = None
        if voice:
            logger.info(f"Procesando archivo de voz para: {username}")
            try:
                # Guardar archivo temporalmente
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                    content = await voice.read()
                    temp_file.write(content)
                    temp_file_path = temp_file.name
                
                # Extraer embedding de voz
                voice_embedding = extract_voice_embedding(temp_file_path)
                logger.info(f"Embedding de voz extraído para: {username}")
                logger.info(f"Tipo de embedding: {type(voice_embedding)}")
                logger.info(f"Forma del embedding: {voice_embedding.shape if hasattr(voice_embedding, 'shape') else 'No tiene shape'}")
                
                # Subir archivo a Azure Storage
                voice_url = upload_voice_recording(content, f"{email}_{int(time.time())}.wav")
                logger.info(f"Archivo de voz subido a Azure: {voice_url}")
                
                # Eliminar archivo temporal
                os.unlink(temp_file_path)
            except Exception as e:
                logger.error(f"Error al procesar archivo de voz: {str(e)}")
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"detail": "Error al procesar el archivo de voz"}
                )
        
        # Crear usuario en la base de datos
        hashed_password = get_password_hash(password)
        logger.info(f"Preparando datos para crear usuario: username={username}, email={email}, voice_embedding={'presente' if voice_embedding is not None else 'ausente'}")
        
        try:
            success = neo4j_client.create_user_with_voice(
                username=username,
                email=email,
                password=hashed_password,
                voice_data=voice_url if voice_url else None,
                voice_embedding=voice_embedding.tolist() if voice_embedding is not None else None
            )
            
            if success:
                process_time = time.time() - start_time
                logger.info(f"Usuario registrado exitosamente: {username} ({email}) - Tiempo: {process_time:.2f}s")
                return {"message": "Usuario registrado exitosamente"}
            else:
                logger.error(f"Error al crear usuario en la base de datos: {username} ({email})")
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"detail": "Error al crear el usuario"}
                )
        except Exception as e:
            logger.error(f"Error al crear usuario: {str(e)}")
            raise
            
    except Exception as e:
        logger.error(f"Error inesperado durante el registro: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Error interno del servidor"}
        )

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Inicia sesión con credenciales (usuario y contraseña)
    """
    try:
        # Verificar credenciales
        user = neo4j_client.verify_user_credentials(form_data.username, form_data.password)
        
        if not user:
            # Intentar verificar con contraseña hasheada
            user_from_db = neo4j_client.get_user_by_email(form_data.username)
            if user_from_db and verify_password(form_data.password, user_from_db.get("password", "")):
                user = user_from_db
            else:
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
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "username": user["username"],
            "email": user["email"]
        }
        
    except Exception as e:
        logger.error(f"Error en el login: {str(e)}")
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en el login: {str(e)}"
        )

@router.post("/login-voice", response_model=Token)
async def login_with_voice(
    email: str = Form(...),
    voice: UploadFile = File(...)
):
    logger.info(f"Iniciando login con voz para email: {email}")
    start_time = time.time()
    
    try:
        # Verificar si el usuario existe
        user = neo4j_client.get_user_by_email(email)
        if not user:
            logger.warning(f"Intento de login con email no registrado: {email}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Credenciales inválidas"}
            )
        
        # Procesar el archivo de voz
        logger.info(f"Procesando archivo de voz para: {email}")
        try:
            # Guardar el archivo temporalmente
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                content = await voice.read()
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            # Extraer embedding de la voz
            logger.info("Extrayendo embedding de la voz")
            voice_embedding = extract_voice_embedding(temp_file_path)
            
            # Obtener embedding almacenado
            stored_embedding = user.get("voice_embedding")
            logger.info(f"Embedding almacenado: {'presente' if stored_embedding is not None else 'ausente'}")
            if stored_embedding is not None:
                logger.info(f"Tipo de embedding almacenado: {type(stored_embedding)}")
                logger.info(f"Longitud del embedding almacenado: {len(stored_embedding) if isinstance(stored_embedding, (list, np.ndarray)) else 'No es una lista/array'}")
            
            if not stored_embedding:
                logger.warning(f"Usuario {email} no tiene embedding de voz almacenado")
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Usuario no tiene voz registrada"}
                )
            
            # Convertir el embedding almacenado a numpy array
            try:
                stored_embedding = np.array(stored_embedding)
                logger.info(f"Embedding convertido a numpy array, forma: {stored_embedding.shape}")
            except Exception as e:
                logger.error(f"Error al convertir embedding a numpy array: {str(e)}")
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"detail": "Error al procesar el embedding de voz"}
                )
            
            # Comparar embeddings
            logger.info("Comparando embeddings de voz")
            similarity = compare_voice_embeddings(voice_embedding, stored_embedding)
            logger.info(f"Similitud de voz: {similarity}")
            
            if similarity < VOICE_SIMILARITY_THRESHOLD:
                logger.warning(f"Autenticación por voz fallida para {email}. Similitud: {similarity}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Voz no reconocida"}
                )
            
            # Crear token de acceso
            logger.info(f"Creando token de acceso para: {email}")
            access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = create_access_token(
                data={"sub": email},
                expires_delta=access_token_expires
            )
            
            # Calcular tiempo de procesamiento
            process_time = time.time() - start_time
            logger.info(f"Login con voz completado para {email}. Tiempo: {process_time:.2f}s")
            
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "username": user["username"],
                "email": user["email"]
            }
            
        except Exception as e:
            logger.error(f"Error al procesar voz para {email}: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Error al procesar la voz"}
            )
        finally:
            # Limpiar archivo temporal
            if 'temp_file_path' in locals():
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.error(f"Error al eliminar archivo temporal: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error en login con voz para {email}: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Error interno del servidor"}
        ) 