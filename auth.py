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
from voice_processing import extract_embedding, compare_voices, verify_voice, preprocess_audio
from azure_storage import upload_voice_recording, download_voice_recording, ensure_azure_storage
from config import (
    SECRET_KEY, 
    ACCESS_TOKEN_EXPIRE_MINUTES, 
    VOICE_SIMILARITY_THRESHOLD,
    ENVIRONMENT,
    IS_PRODUCTION
)
from pydantic import BaseModel
import librosa
import numpy as np

# Configurar logging
logging.basicConfig(
    level=logging.INFO if IS_PRODUCTION else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('auth.log')
    ]
)
logger = logging.getLogger(__name__)

# Log del entorno actual
logger.info(f"Ejecutando en entorno: {ENVIRONMENT}")

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

        # Hashear la contraseña
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        logger.debug(f"Contraseña hasheada para: {email}")

        # Procesar la grabación de voz si se proporciona
        voice_embedding = None
        voice_embeddings = None
        voice_url = None
        temp_file = None
        
        if voice_recording:
            logger.info("Procesando grabación de voz")
            
            # Verificar disponibilidad de Azure Storage si se va a subir una grabación
            if not await ensure_azure_storage():
                logger.warning("⚠️ Azure Storage no está disponible. El usuario se registrará sin voz.")
                # No lanzamos excepción para permitir el registro sin voz
            else:
                # Crear directorio temporal
                temp_dir = "./temp_files"
                if not os.path.exists(temp_dir):
                    os.makedirs(temp_dir)
                    
                # Guardar archivo temporalmente
                temp_file = f"{temp_dir}/temp_{voice_recording.filename}"
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
                        logger.warning("⚠️ No se pudo extraer el embedding de la voz. El usuario se registrará sin funcionalidad de voz.")
                        # No falla el registro, simplemente se crea el usuario sin embedding de voz
                    else:
                        # Crear lista de embeddings
                        voice_embeddings = [voice_embedding]
                        
                        # Subir a Azure Storage
                        voice_url = await upload_voice_recording(temp_file, email)
                        if not voice_url:
                            logger.error("❌ No se pudo subir la grabación a Azure Storage")
                            # Continuar sin URL de voz, pero con embedding
                        else:
                            logger.info(f"📤 Archivo subido a Azure. URL: {voice_url}")
                finally:
                    # Limpiar archivo temporal
                    if temp_file and os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.debug("🧹 Archivo temporal eliminado")

        # Crear usuario
        logger.info("Creando usuario en MongoDB")
        success = mongo_client.create_user(
            username=username,
            email=email,
            password=hashed_password,  # Usar la contraseña hasheada
            voice_embedding=voice_embedding,
            voice_embeddings=voice_embeddings,
            voice_url=voice_url
        )

        if success:
            logger.info(f"✅ Usuario registrado exitosamente: {email}")
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
            logger.error(f"❌ Error al crear usuario en la base de datos: {email}")
            raise HTTPException(status_code=500, detail="Error al crear el usuario")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al registrar usuario: {str(e)}")
        raise HTTPException(status_code=500, detail="Error en el servidor")

@router.post("/login", response_model=LoginResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Inicia sesión con credenciales (usuario y contraseña)
    """
    try:
        email = form_data.username  # En OAuth2PasswordRequestForm el email se envía como username
        logger.info(f"🔑 Intento de inicio de sesión para: {email}")
        
        # Hashear la contraseña
        hashed_password = hashlib.sha256(form_data.password.encode()).hexdigest()
        logger.debug(f"Contraseña hasheada para login: {email}")
        
        # Verificar credenciales
        user = mongo_client.verify_user_credentials(email, hashed_password)
        if not user:
            logger.warning(f"❌ Credenciales incorrectas para: {email}")
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
        
        logger.info(f"✅ Login exitoso para: {email}")
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            username=user.get("username"),
            email=user["email"],
            voice_url=user.get("voice_url")
        )
        
    except Exception as e:
        logger.error(f"❌ Error en el login: {str(e)}")
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
    # Inicializar variable para evitar error de referencia
    temp_file = None
    
    try:
        logger.info(f"🎤 Intento de login con voz para: {email}")
        
        # Verificar tamaño del archivo
        content = await voice_recording.read()
        if len(content) > 15 * 1024 * 1024:  # 15MB
            logger.warning(f"❌ Archivo demasiado grande: {len(content)} bytes")
            raise HTTPException(status_code=400, detail="El archivo de audio es demasiado grande (máximo 15MB)")
            
        if len(content) == 0:
            logger.warning("❌ Archivo vacío")
            raise HTTPException(status_code=400, detail="El archivo de audio está vacío")
        
        # Buscar usuario por email
        user = mongo_client.get_user_by_email(email)
        if not user:
            logger.warning(f"❌ Usuario no encontrado: {email}")
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        # Verificar que el usuario tenga una voz registrada
        if not user.get('voice_url'):
            logger.warning(f"⚠️ Usuario {email} no tiene voz registrada")
            raise HTTPException(status_code=400, detail="No hay voz registrada para este usuario")

        logger.info(f"🔍 Voice URL del usuario: {user['voice_url']}")
        
        # Verificar si el usuario tiene embeddings de voz registrados
        if not user.get('voice_embedding') and not user.get('voice_embeddings'):
            logger.warning(f"⚠️ Usuario {email} no tiene embeddings de voz registrados")
            raise HTTPException(status_code=400, detail="No hay datos de voz registrados para este usuario")
            
        # Crear directorio temporal
        temp_dir = "./temp_files"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        # Guardar el archivo temporal de la grabación
        temp_file = f"{temp_dir}/temp_{voice_recording.filename}"
        with open(temp_file, "wb") as buffer:
            buffer.write(content)
            logger.info(f"💾 Archivo de voz guardado: {temp_file} ({len(content)} bytes)")
        
        # Importamos verify_voice (usando una instancia temporal del router)
        from voice_processing import verify_voice as voice_verifier
        
        # Preprocesar audio y extraer embedding
        from voice_processing import preprocess_audio, extract_embedding
        
        try:
            # Preprocesar audio
            preprocess_audio(temp_file)
            
            # Extraer embedding
            input_embedding = extract_embedding(temp_file)
            
            if input_embedding is None:
                raise HTTPException(
                    status_code=400,
                    detail="No se pudo procesar el audio. Intente nuevamente en un entorno más silencioso."
                )
                
            # Obtener embeddings del usuario desde MongoDB
            user_data = mongo_client.get_user_voice_data(email)
            
            # Verificar contra múltiples embeddings y tomar el mejor resultado
            best_similarity = 0
            is_match = False
            
            # Verificar contra la galería de embeddings si existe
            for stored_embedding in user_data.get('voice_embeddings', []):
                from voice_processing import compare_voices
                result = compare_voices(input_embedding, stored_embedding)
                if result["similarity"] > best_similarity:
                    best_similarity = result["similarity"]
                    is_match = result["match"]
                    
            # Si no hay galería, verificar con el embedding principal
            if not user_data.get('voice_embeddings') and user_data.get('voice_embedding'):
                from voice_processing import compare_voices
                result = compare_voices(input_embedding, user_data['voice_embedding'])
                best_similarity = result["similarity"]
                is_match = result["match"]
            
            # Verificar si la voz coincide
            if not is_match:
                logger.warning(f"❌ Similitud insuficiente: {best_similarity:.2f} < {VOICE_SIMILARITY_THRESHOLD}")
                raise HTTPException(status_code=401, detail="La voz no coincide")
            
            # Si llegamos aquí, la voz coincide
            logger.info(f"✅ Login exitoso para {email} con similitud {best_similarity:.2f}")
            
            # Crear token
            access_token = create_access_token(data={"sub": email})
            
            return LoginResponse(
                access_token=access_token,
                token_type="bearer",
                username=user.get("username"),
                email=email,
                voice_url=user.get("voice_url")
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al procesar la voz: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Error al procesar la voz"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error en login con voz: {str(e)}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="Error al procesar la autenticación por voz"
        )
    finally:
        # Limpiar archivos temporales
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                logger.debug("🧹 Archivo temporal eliminado")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar archivo temporal: {str(e)}")

@router.get("/me", response_model=LoginResponse)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return LoginResponse(
        access_token="",  # No es necesario devolver el token aquí
        token_type="bearer",
        username=current_user.get("username"),
        email=current_user["email"],
        voice_url=current_user.get("voice_url")
    ) 