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
from azure_storage import upload_voice_recording, download_voice_recording, ensure_azure_storage, upload_face_photo
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
import face_recognition
import cv2
import time
import warnings
import onnxruntime as ort
from insightface.app import FaceAnalysis
import contextlib
import io
import requests
from urllib.parse import urlparse
import tempfile

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
    face_url: Optional[str] = None

# Suprimir warnings molestos
warnings.filterwarnings("ignore")

# Silenciar logs internos de onnxruntime
ort.set_default_logger_severity(3)

# ------------------ PREPROCESAMIENTO ------------------ #
def preprocess_image(image):
    height, width = image.shape[:2]
    max_size = 800
    if height > max_size or width > max_size:
        scale = max_size / max(height, width)
        image = cv2.resize(image, (int(width * scale), int(height * scale)))
    
    lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    lab = cv2.merge((l, a, b))
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    
    return enhanced

# ------------------ ARCFACE COMPARISON ------------------ #
def compare_faces_arcface(image_path1, image_path2, threshold=0.65):
    if not os.path.exists(image_path1) or not os.path.exists(image_path2):
        return "One or both image files do not exist", None, None

    start_time = time.time()

    img1 = cv2.imread(image_path1)
    img2 = cv2.imread(image_path2)

    if img1 is None or img2 is None:
        return "Error loading one or both images", None, None

    img1_rgb = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
    img2_rgb = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)

    img1_processed = preprocess_image(img1_rgb)
    img2_processed = preprocess_image(img2_rgb)

    # Silenciar los prints del modelo durante su inicialización
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        face_analyzer = FaceAnalysis(providers=['CPUExecutionProvider'])
        face_analyzer.prepare(ctx_id=0, det_size=(640, 640))

    faces1 = face_analyzer.get(cv2.cvtColor(img1_processed, cv2.COLOR_RGB2BGR))
    faces2 = face_analyzer.get(cv2.cvtColor(img2_processed, cv2.COLOR_RGB2BGR))

    if not faces1 or not faces2:
        return "No faces detected in one or both images", None, None

    embedding1 = faces1[0].embedding
    embedding2 = faces2[0].embedding

    cosine_sim = np.dot(embedding1, embedding2) / (np.linalg.norm(embedding1) * np.linalg.norm(embedding2))
    similarity_percentage = cosine_sim * 100
    match = cosine_sim >= threshold

    execution_time = time.time() - start_time

    return match, similarity_percentage, execution_time

# Función para descargar imagen desde URL
def download_image(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # Crear un archivo temporal
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            temp_file.write(response.content)
            temp_file.close()
            return temp_file.name
        return None
    except Exception as e:
        logger.error(f"Error downloading image: {str(e)}")
        return None

@router.post("/register", response_model=LoginResponse)
async def register(
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    voice_recording: UploadFile = File(None),
    face_photo: UploadFile = File(None)
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
        face_url = None
        
        if voice_recording:
            logger.info("Procesando grabación de voz")
            logger.info(f"Nombre del archivo: {voice_recording.filename}")
            logger.info(f"Tipo de contenido: {voice_recording.content_type}")
            
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
                            logger.error("❌ El archivo de voz está vacío")
                            raise HTTPException(status_code=400, detail="El archivo de voz está vacío")
                        
                        content_size = len(content)
                        logger.info(f"Tamaño del contenido: {content_size} bytes")
                        
                        buffer.write(content)
                        logger.info(f"Archivo de voz guardado temporalmente: {temp_file}")
                        
                        # Verificar que el archivo se escribió correctamente
                        if os.path.exists(temp_file):
                            file_size = os.path.getsize(temp_file)
                            logger.info(f"Tamaño del archivo guardado: {file_size} bytes")
                            if file_size == 0:
                                logger.error("❌ El archivo guardado está vacío")
                        else:
                            logger.error("❌ El archivo no se guardó correctamente")
                except Exception as e:
                    logger.error(f"❌ Error al guardar el archivo de voz: {str(e)}")
                    if temp_file and os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.debug("🧹 Archivo temporal eliminado por error")
                    raise HTTPException(status_code=500, detail="Error al procesar el archivo de voz")

                # Extraer embedding
                try:
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
                    # Limpiar archivo temporal después de procesarlo
                    if temp_file and os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.debug("🧹 Archivo temporal eliminado después de procesamiento")
        
        if face_photo:
            logger.info("Procesando foto de rostro")
            # Crear directorio temporal
            temp_dir = "./temp_files"
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            image_file = f"{temp_dir}/face.jpg"
            with open(image_file, "wb") as buffer:
                content = await face_photo.read()
                buffer.write(content)
                logger.info(f"Foto de rostro guardada temporalmente: {image_file}")
            
            # Subir a Azure Storage
            face_url = await upload_face_photo(image_file, email)
            if not face_url:
                logger.error("❌ No se pudo subir la foto de rostro a Azure Storage")
            else:
                logger.info(f"📤 Foto de rostro subida a Azure. URL: {face_url}")
            
        # Crear usuario
        logger.info("Creando usuario en MongoDB")
        success = mongo_client.create_user(
            username=username,
            email=email,
            password=hashed_password,  # Usar la contraseña hasheada
            voice_embedding=voice_embedding,
            voice_embeddings=voice_embeddings,
            voice_url=voice_url,
            face_url=face_url,
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
                voice_url=voice_url,
                face_url=face_url,
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
        access_token="",
        token_type="bearer",
        username=current_user.get("username"),
        email=current_user["email"],
        voice_url=current_user.get("voice_url")
    )

@router.post("/login_face", response_model=LoginResponse)
async def login_face(
    email: str = Form(...),
    face_photo: UploadFile = File(...)
):
    try:
        logger.info(f"📸 Intento de login con foto para: {email}")
        
        # Verificar tamaño del archivo
        content = await face_photo.read()
        if len(content) > 5 * 1024 * 1024:  # 5MB
            logger.warning(f"❌ Archivo demasiado grande: {len(content)} bytes")
            raise HTTPException(status_code=400, detail="La foto es demasiado grande (máximo 5MB)")
            
        if len(content) == 0:
            logger.warning("❌ Archivo vacío")
            raise HTTPException(status_code=400, detail="La foto está vacía")
        
        # Buscar usuario por email
        user = mongo_client.get_user_by_email(email)
        if not user:
            logger.warning(f"❌ Usuario no encontrado: {email}")
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        # Verificar que el usuario tenga una foto registrada
        if not user.get('face_url'):
            logger.warning(f"⚠️ Usuario {email} no tiene foto registrada")
            raise HTTPException(status_code=400, detail="No hay foto registrada para este usuario")

        logger.info(f"🔍 Face URL del usuario: {user['face_url']}")
        
        # Crear directorio temporal
        temp_dir = "./temp_files"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        # Guardar el archivo temporal de la foto recibida
        temp_file_received = f"{temp_dir}/temp_{face_photo.filename}"
        with open(temp_file_received, "wb") as buffer:
            buffer.write(content)
            logger.info(f"Foto recibida guardada: {temp_file_received} ({len(content)} bytes)")

        # Descargar la foto registrada
        temp_file_registered = download_image(user['face_url'])
        if not temp_file_registered:
            raise HTTPException(status_code=500, detail="Error al descargar la foto registrada")

        logger.info("🔄 Iniciando comparación facial...")
        
        # Realizar la comparación facial
        match, similarity, exec_time = compare_faces_arcface(temp_file_received, temp_file_registered)
        
        logger.info(f"📊 Resultados de la comparación:")
        logger.info(f"   - Coincidencia: {match}")
        logger.info(f"   - Similitud: {similarity:.2f}%")
        logger.info(f"   - Tiempo de ejecución: {exec_time:.2f} segundos")

        # Limpiar archivos temporales
        if os.path.exists(temp_file_received):
            os.remove(temp_file_received)
        if os.path.exists(temp_file_registered):
            os.remove(temp_file_registered)
            
        if match:
            # Generar token de acceso
            access_token = create_access_token(data={"sub": email})
            logger.info(f"✅ Login exitoso para: {email}")
            return LoginResponse(
                access_token=access_token,
                token_type="bearer",
                username=user.get("username"),
                email=email,
                voice_url=user.get("voice_url"),
                face_url=user.get("face_url")
            )
        else:
            logger.warning(f"❌ Autenticación facial fallida para: {email}")
            raise HTTPException(
                status_code=401,
                detail="La autenticación facial falló. Las caras no coinciden."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error en login con foto: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error al procesar la autenticación por foto"
        ) 