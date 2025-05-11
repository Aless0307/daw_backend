from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from datetime import timedelta
from typing import Optional, Dict, List # Importar List si voice_embeddings es una lista
import logging
import hashlib
import os
from utils.auth_utils import create_access_token, get_current_user
# Asegúrate de que la importación de MongoDBClient sea correcta para tu estructura de proyecto
from mongodb_client import MongoDBClient
# Asegúrate de que las importaciones de voice_processing sean correctas
from voice_processing import extract_embedding, compare_voices, verify_voice, preprocess_audio
# Asegúrate de que las importaciones de azure_storage sean correctas
from azure_storage import upload_voice_recording, download_voice_recording, ensure_azure_storage, upload_face_photo
# Asegúrate de que la importación de config sea correcta
from config import (
    SECRET_KEY,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    VOICE_SIMILARITY_THRESHOLD,
    ENVIRONMENT,
    IS_PRODUCTION,
    ALLOWED_ORIGINS # Importar ALLOWED_ORIGINS para la config de CORS
)
# Importaciones para Pydantic y BSON
from pydantic import BaseModel, Field
from bson import ObjectId # Necesario para la serialización de ObjectId
from fastapi.middleware.cors import CORSMiddleware # Importar CORSMiddleware

# Otras importaciones que ya tenías
import librosa
import numpy as np
import face_recognition
import cv2
import time
import warnings
import onnxruntime as ort
# Asegúrate de que la importación de face_model sea correcta
from face_model import face_analyzer
import contextlib
import io
import requests
from urllib.parse import urlparse
import tempfile
import traceback # Para imprimir stack trace en errores

# importar el router para los ejercicios
from routers.logic import router as logic_router
##################################################

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

# Log del entorno actual para saber si estaba en desarrollo o en railway
logger.info(f"Ejecutando en entorno: {ENVIRONMENT}")

router = APIRouter()
mongo_client = MongoDBClient()
router.include_router(logic_router, prefix="/api") #añadimos el router para los ejercicios

# ----- Configurar CORS (Asegúrate de que ALLOWED_ORIGINS no contenga "*" si allow_credentials es True) -----
CORS_CONFIG = {
    "allow_origins": ALLOWED_ORIGINS, # Debe contener las URLs exactas de tu frontend (ej: ["http://localhost:5173", "https://daw-frontend.vercel.app"])
    "allow_credentials": True, # Necesario si tu frontend envía cookies o headers de Authorization
    "allow_methods": ["*"], # O especifica solo los métodos que usas (GET, POST, OPTIONS, etc.)
    "allow_headers": ["*"], # O especifica solo los headers que usas (Authorization, Content-Type, etc.)
}

# Asumiendo que 'app' es tu instancia principal de FastAPI definida en otro lugar (ej: main.py)
# Debes añadir este middleware a tu instancia principal de FastAPI, no necesariamente aquí
# app.add_middleware(
#     CORSMiddleware,
#     **CORS_CONFIG
# )
# Si este archivo es solo el router, la configuración de CORS debe estar en el archivo principal de la app FastAPI.


# ----- Definición de Modelos Pydantic -----

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

# --- NUEVO MODELO PARA LA RESPUESTA DEL ENDPOINT user_by_email ---
class UserResponseModel(BaseModel):
    # Mapea el campo '_id' de MongoDB (ObjectId) a 'id' en el modelo y JSON
    id: str = Field(alias='_id')

    # Añade aquí los otros campos del usuario que quieres retornar
    email: str
    username: Optional[str] = None # Asumiendo que username puede ser opcional

    # Añade otros campos si tu documento de usuario los tiene y quieres retornarlos
    # voice_url: Optional[str] = None
    # face_url: Optional[str] = None

    class Config:
        # Configuración para Pydantic V2+
        populate_by_name = True # Permite mapear por alias ('_id' a 'id')

        # Configuración para serializar ObjectId a string
        # Aunque definimos esto, añadiremos una conversión explícita abajo como respaldo
        json_encoders = {ObjectId: str} # Para Pydantic V1 y V2

        # Para Pydantic V2+, también puedes añadir ejemplos para la documentación
        # json_schema_extra = {
        #     "examples": [
        #         {
        #             "id": "60d5ec49b8f9c40e6c1a0d9e",
        #             "email": "test@example.com",
        #             "username": "testuser"
        #         }
        #     ]
        # }


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
        logger.error("One or both image files do not exist")
        return "One or both image files do not exist", None, None

    start_time = time.time()

    img1 = cv2.imread(image_path1)
    img2 = cv2.imread(image_path2)

    if img1 is None or img2 is None:
        logger.error("Error loading one or both images")
        return "Error loading one or both images", None, None

    img1_rgb = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
    img2_rgb = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)

    img1_processed = preprocess_image(img1_rgb)
    img2_processed = preprocess_image(img2_rgb)

    # Silenciar los prints del modelo durante su inicialización
    # Esto parece ser un remanente de depuración, considera eliminarlo si no es necesario
    # f = io.StringIO()
    # with contextlib.redirect_stdout(f):
    faces1 = face_analyzer.get(cv2.cvtColor(img1_processed, cv2.COLOR_RGB2BGR))
    faces2 = face_analyzer.get(cv2.cvtColor(img2_processed, cv2.COLOR_RGB2BGR))


    if not faces1 or not faces2:
        logger.warning("No faces detected in one or both images")
        return "No faces detected in one or both images", None, None

    embedding1 = faces1[0].embedding
    embedding2 = faces2[0].embedding

    cosine_sim = np.dot(embedding1, embedding2) / (np.linalg.norm(embedding1) * np.linalg.norm(embedding2))
    similarity_percentage = cosine_sim * 100
    match = cosine_sim >= threshold

    execution_time = time.time() - start_time
    logger.debug(f"Face comparison done in {execution_time:.4f} seconds")

    return match, similarity_percentage, execution_time

# Función para descargar imagen desde URL
def download_image(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # Crear un archivo temporal
            # Usar delete=False para que el archivo no se elimine inmediatamente al cerrarse
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            temp_file.write(response.content)
            temp_file.close() # Cerrar el archivo para poder usar su nombre
            logger.debug(f"Downloaded image to temporary file: {temp_file.name}")
            return temp_file.name
        else:
            logger.error(f"Error downloading image from {url}: Status code {response.status_code}")
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
    # Inicializar variables para limpieza final
    temp_voice_file = None
    temp_face_file = None

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
        voice_embeddings = None # Considera si quieres almacenar múltiples embeddings al registrar
        voice_url = None

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
                # Usar tempfile para nombres únicos y manejo más seguro
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{voice_recording.filename}") as tmp:
                    temp_voice_file = tmp.name
                    content = await voice_recording.read()
                    if not content:
                        logger.error("❌ El archivo de voz está vacío")
                        raise HTTPException(status_code=400, detail="El archivo de voz está vacío")

                    content_size = len(content)
                    logger.info(f"Tamaño del contenido: {content_size} bytes")
                    tmp.write(content)
                    logger.info(f"Archivo de voz guardado temporalmente: {temp_voice_file}")

                # Verificar que el archivo se escribió correctamente
                if os.path.exists(temp_voice_file):
                    file_size = os.path.getsize(temp_voice_file)
                    logger.info(f"Tamaño del archivo guardado: {file_size} bytes")
                    if file_size == 0:
                        logger.error("❌ El archivo guardado está vacío")
                        raise HTTPException(status_code=400, detail="El archivo de voz guardado está vacío")
                else:
                    logger.error("❌ El archivo no se guardó correctamente")
                    raise HTTPException(status_code=500, detail="Error al guardar el archivo de voz")


                # Extraer embedding
                try:
                    # Asegúrate de que preprocess_audio maneje el path correctamente
                    preprocess_audio(temp_voice_file) # Preprocesar el archivo temporal
                    voice_embedding = extract_embedding(temp_voice_file) # Extraer del archivo temporal

                    if voice_embedding is None:
                        logger.warning("⚠️ No se pudo extraer el embedding de la voz. El usuario se registrará sin funcionalidad de voz.")
                        # No falla el registro, simplemente se crea el usuario sin embedding de voz
                    else:
                         # Aquí podrías decidir si guardar solo el último embedding o una lista
                         # Si quieres una lista, inicialízala y añade el embedding
                        voice_embeddings = [voice_embedding.tolist()] # Convertir a lista para guardar en MongoDB


                        # Subir a Azure Storage
                        voice_url = await upload_voice_recording(temp_voice_file, email)
                        if not voice_url:
                            logger.error("❌ No se pudo subir la grabación a Azure Storage")
                            # Continuar sin URL de voz, pero con embedding
                        else:
                            logger.info(f"📤 Archivo subido a Azure. URL: {voice_url}")
                except Exception as e:
                     logger.error(f"❌ Error durante el procesamiento o subida de voz: {str(e)}")
                     # Considera si quieres lanzar una HTTPException aquí o simplemente loguear y continuar
                     # raise HTTPException(status_code=500, detail="Error al procesar o subir la grabación de voz")


        if face_photo:
            logger.info("Procesando foto de rostro")
            # Crear directorio temporal
            temp_dir = "./temp_files"
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)

            # Guardar archivo temporalmente
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{face_photo.filename}") as tmp:
                temp_face_file = tmp.name
                content = await face_photo.read()
                if not content:
                     logger.error("❌ El archivo de foto está vacío")
                     raise HTTPException(status_code=400, detail="El archivo de foto está vacío")
                tmp.write(content)
                logger.info(f"Foto de rostro guardada temporalmente: {temp_face_file}")

            # Subir a Azure Storage
            face_url = await upload_face_photo(temp_face_file, email)
            if not face_url:
                logger.error("❌ No se pudo subir la foto de rostro a Azure Storage")
                # Considera si quieres lanzar una HTTPException aquí o simplemente loguear y continuar
                # raise HTTPException(status_code=500, detail="Error al subir la foto de rostro")
            else:
                logger.info(f"📤 Foto de rostro subida a Azure. URL: {face_url}")


        # Crear usuario
        logger.info("Creando usuario en MongoDB")
        # Asegúrate de que create_user pueda manejar voice_embedding y voice_embeddings (lista)
        success = mongo_client.create_user(
            username=username,
            email=email,
            password=hashed_password,  # Usar la contraseña hasheada
            voice_embedding=voice_embedding.tolist() if voice_embedding is not None else None, # Guardar como lista si existe
            voice_embeddings=voice_embeddings, # Guardar la lista si se generó
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
        # Si ya es una HTTPException, simplemente la relanzamos
        raise
    except Exception as e:
        # Para otros errores, logueamos el stack trace y retornamos un 500
        logger.error(f"❌ Error al registrar usuario: {str(e)}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Error en el servidor")
    finally:
        # Limpiar archivos temporales
        if temp_voice_file and os.path.exists(temp_voice_file):
            try:
                os.remove(temp_voice_file)
                logger.debug(f"🧹 Archivo temporal de voz eliminado: {temp_voice_file}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar archivo temporal de voz {temp_voice_file}: {str(e)}")
        if temp_face_file and os.path.exists(temp_face_file):
            try:
                os.remove(temp_face_file)
                logger.debug(f"🧹 Archivo temporal de foto eliminado: {temp_face_file}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar archivo temporal de foto {temp_face_file}: {str(e)}")


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
        # Asegúrate de que verify_user_credentials retorna un diccionario con 'email', 'username', 'voice_url', etc.
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
            username=user.get("username"), # Usar .get() para evitar KeyError si el campo no existe
            email=user["email"],
            voice_url=user.get("voice_url"),
            face_url=user.get("face_url") # Incluir face_url en la respuesta de login
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error en el login: {str(e)}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en el login: {str(e)}"
        )

@router.post("/login-voice", response_model=LoginResponse)
async def login_with_voice(
    email: str = Form(...),
    voice_recording: UploadFile = File(...)
):
    # Inicializar variable para limpieza final
    temp_file = None

    try:
        logger.info(f"🎤 Intento de login con voz para: {email}")

        # Verificar tamaño del archivo
        # Leer el contenido una vez para verificar el tamaño y luego usarlo
        content = await voice_recording.read()
        content_size = len(content)

        if content_size > 15 * 1024 * 1024:  # 15MB
            logger.warning(f"❌ Archivo demasiado grande: {content_size} bytes")
            raise HTTPException(status_code=400, detail="El archivo de audio es demasiado grande (máximo 15MB)")

        if content_size == 0:
            logger.warning("❌ Archivo vacío")
            raise HTTPException(status_code=400, detail="El archivo de audio está vacío")

        # Buscar usuario por email
        # Asegúrate de que get_user_by_email retorna un diccionario
        user = mongo_client.get_user_by_email(email)
        if not user:
            logger.warning(f"❌ Usuario no encontrado: {email}")
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        # Verificar que el usuario tenga una voz registrada (URL o embeddings)
        if not user.get('voice_url') and not user.get('voice_embedding') and not user.get('voice_embeddings'):
             logger.warning(f"⚠️ Usuario {email} no tiene datos de voz registrados")
             raise HTTPException(status_code=400, detail="No hay datos de voz registrados para este usuario")


        # Crear directorio temporal
        temp_dir = "./temp_files"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # Guardar el archivo temporal de la grabación
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{voice_recording.filename}") as tmp:
            temp_file = tmp.name
            tmp.write(content) # Escribir el contenido ya leído
            logger.info(f"💾 Archivo de voz guardado: {temp_file} ({content_size} bytes)")


        # Importamos verify_voice (usando una instancia temporal del router) - Esto parece incorrecto.
        # verify_voice debería ser una función o clase importada directamente.
        # from voice_processing import verify_voice as voice_verifier # Esto importa la función, no una instancia de router

        # Preprocesar audio y extraer embedding
        # Asegúrate de que estas funciones estén correctamente definidas en voice_processing.py
        from voice_processing import preprocess_audio, extract_embedding

        try:
            # Preprocesar audio
            # Asegúrate de que preprocess_audio maneje el path correctamente
            preprocess_audio(temp_file)

            # Extraer embedding
            # Asegúrate de que extract_embedding maneje el path correctamente y retorne un numpy array o None
            input_embedding = extract_embedding(temp_file)

            if input_embedding is None:
                logger.warning("❌ No se pudo extraer el embedding de la voz del audio recibido.")
                raise HTTPException(
                    status_code=400,
                    detail="No se pudo procesar el audio. Intente nuevamente en un entorno más silencioso."
                )

            # Obtener embeddings del usuario desde MongoDB
            # Asegúrate de que get_user_voice_data retorna un diccionario con 'voice_embedding' y 'voice_embeddings'
            user_voice_data = mongo_client.get_user_voice_data(email)

            # Verificar contra múltiples embeddings y tomar el mejor resultado
            best_similarity = 0
            is_match = False

            # Convertir embeddings almacenados (si son listas) a numpy arrays para la comparación
            stored_embeddings = user_voice_data.get('voice_embeddings', [])
            if user_voice_data.get('voice_embedding') is not None:
                 # Si hay un embedding principal y no hay lista, usarlo
                 if not stored_embeddings:
                      stored_embeddings = [user_voice_data['voice_embedding']]
                 else:
                      # Si hay lista y embedding principal, añadir el principal a la lista si no está ya
                      # Esto depende de tu lógica de almacenamiento
                      pass # Opcional: Añadir el embedding principal a stored_embeddings si no está


            # Asegurarse de que los embeddings almacenados son numpy arrays antes de comparar
            processed_stored_embeddings = []
            for emb in stored_embeddings:
                 if isinstance(emb, list):
                      processed_stored_embeddings.append(np.array(emb))
                 elif isinstance(emb, np.ndarray):
                      processed_stored_embeddings.append(emb)
                 # Manejar otros tipos si es necesario


            # Verificar contra la galería de embeddings procesados
            if processed_stored_embeddings:
                from voice_processing import compare_voices # Asegúrate de que compare_voices esté aquí
                for stored_embedding_np in processed_stored_embeddings:
                    result = compare_voices(input_embedding, stored_embedding_np)
                    if result["similarity"] > best_similarity:
                        best_similarity = result["similarity"]
                        is_match = result["match"]

            # Si no se encontró ningún embedding almacenado válido
            if not processed_stored_embeddings:
                 logger.warning(f"⚠️ Usuario {email} no tiene embeddings de voz válidos almacenados.")
                 raise HTTPException(status_code=400, detail="No hay datos de voz válidos registrados para este usuario")


            # Verificar si la voz coincide (usando el mejor resultado de similitud)
            # Asegúrate de que VOICE_SIMILARITY_THRESHOLD esté importado y sea un valor numérico
            if not is_match or best_similarity < VOICE_SIMILARITY_THRESHOLD:
                logger.warning(f"❌ Similitud insuficiente: {best_similarity:.2f} < {VOICE_SIMILARITY_THRESHOLD}")
                raise HTTPException(status_code=401, detail="La voz no coincide")

            # Si llegamos aquí, la voz coincide
            logger.info(f"✅ Login exitoso para {email} con similitud {best_similarity:.2f}")

            # Crear token
            access_token = create_access_token(data={"sub": email})

            # Asegúrate de que user es un diccionario y contiene los campos necesarios
            return LoginResponse(
                access_token=access_token,
                token_type="bearer",
                username=user.get("username"),
                email=user["email"],
                voice_url=user.get("voice_url"),
                face_url=user.get("face_url") # Incluir face_url
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error durante el procesamiento o comparación de voz: {str(e)}")
            import traceback
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise HTTPException(
                status_code=500,
                detail="Error al procesar la voz" # Mensaje genérico para el frontend
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error general en login con voz: {str(e)}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="Error al procesar la autenticación por voz" # Mensaje genérico para el frontend
        )
    finally:
        # Limpiar archivos temporales
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                logger.debug(f"🧹 Archivo temporal de voz eliminado: {temp_file}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar archivo temporal de voz {temp_file}: {str(e)}")


@router.get("/me", response_model=LoginResponse)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    # get_current_user debe retornar un diccionario con los datos del usuario
    # Asegúrate de que current_user contiene 'email', 'username', 'voice_url', 'face_url'
    return LoginResponse(
        access_token="", # No retornamos el token de acceso aquí por seguridad (ya lo tiene el frontend)
        token_type="bearer",
        username=current_user.get("username"),
        email=current_user["email"], # El email debe estar siempre presente si el usuario está autenticado
        voice_url=current_user.get("voice_url"),
        face_url=current_user.get("face_url")
    )

@router.post("/login_face", response_model=LoginResponse)
async def login_face(
    email: str = Form(...),
    face_photo: UploadFile = File(...)
):
    # Inicializar variables para limpieza final
    temp_file_received = None
    temp_file_registered = None

    try:
        logger.info(f"📸 Intento de login con foto para: {email}")

        # Verificar tamaño del archivo
        content = await face_photo.read()
        content_size = len(content)

        if content_size > 5 * 1024 * 1024:  # 5MB
            logger.warning(f"❌ Archivo demasiado grande: {content_size} bytes")
            raise HTTPException(status_code=400, detail="La foto es demasiado grande (máximo 5MB)")

        if content_size == 0:
            logger.warning("❌ Archivo vacío")
            raise HTTPException(status_code=400, detail="La foto está vacía")

        # Buscar usuario por email
        # Asegúrate de que get_user_by_email retorna un diccionario
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
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{face_photo.filename}") as tmp:
            temp_file_received = tmp.name
            tmp.write(content) # Escribir el contenido ya leído
            logger.info(f"Foto recibida guardada: {temp_file_received} ({content_size} bytes)")

        # Descargar la foto registrada
        temp_file_registered = download_image(user['face_url'])
        if not temp_file_registered or not os.path.exists(temp_file_registered):
            logger.error(f"❌ No se pudo descargar o encontrar la foto registrada para {email}")
            raise HTTPException(status_code=500, detail="Error al descargar la foto registrada")

        logger.info("🔄 Iniciando comparación facial...")

        # Realizar la comparación facial
        match, similarity, exec_time = compare_faces_arcface(temp_file_received, temp_file_registered)

        logger.info(f"📊 Resultados de la comparación:")
        logger.info(f"   - Coincidencia: {match}")
        logger.info(f"   - Similitud: {similarity:.2f}%")
        logger.info(f"   - Tiempo de ejecución: {exec_time:.2f} segundos")

        # Limpiar archivos temporales de inmediato (antes de la verificación 'match')
        # Ya usamos finally para esto, así que no es estrictamente necesario aquí, pero puede ayudar a liberar espacio antes.
        # if os.path.exists(temp_file_received):
        #     os.remove(temp_file_received)
        # if os.path.exists(temp_file_registered):
        #     os.remove(temp_file_registered)


        if match:
            # Generar token de acceso
            access_token = create_access_token(data={"sub": email})
            logger.info(f"✅ Login exitoso para: {email}")
            # Asegúrate de que user es un diccionario y contiene los campos necesarios
            return LoginResponse(
                access_token=access_token,
                token_type="bearer",
                username=user.get("username"),
                email=user["email"],
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
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="Error al procesar la autenticación por foto"
        )
    finally:
        # Limpiar archivos temporales
        if temp_file_received and os.path.exists(temp_file_received):
            try:
                os.remove(temp_file_received)
                logger.debug(f"🧹 Archivo temporal de foto recibida eliminado: {temp_file_received}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar archivo temporal de foto recibida {temp_file_received}: {str(e)}")
        if temp_file_registered and os.path.exists(temp_file_registered):
            try:
                os.remove(temp_file_registered)
                logger.debug(f"🧹 Archivo temporal de foto registrada eliminado: {temp_file_registered}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar archivo temporal de foto registrada {temp_file_registered}: {str(e)}")


# --- ENDPOINT CORREGIDO user_by_email ---
@router.get("/user_by_email", response_model=UserResponseModel) # <-- Usamos el modelo Pydantic aquí
async def user_by_email(email: str):
    """
    Obtiene los datos básicos de un usuario por su email.
    Retorna el ID del usuario como string.
    """
    logger.info(f"📥 GET /auth/user_by_email para email: {email}")
    # Asumimos que mongo_client.get_user_by_email retorna un DICCIONARIO de PyMongo
    user_document = mongo_client.get_user_by_email(email)

    if not user_document:
        logger.warning(f"❌ Usuario no encontrado para email: {email}")
        # FastAPI maneja esta excepción y retorna un 404
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # --- EXPLICIT CONVERSION TO STRING ---
    # This is a fallback in case json_encoders is not working as expected
    if isinstance(user_document, dict) and '_id' in user_document and isinstance(user_document['_id'], ObjectId):
        user_document['_id'] = str(user_document['_id'])
        logger.debug(f"DEBUG BACKEND: Converted ObjectId to string for _id: {user_document['_id']}")
    # Note: If user_document is not a dict but some custom object, this check needs adjustment.
    # Assuming it's a dict based on typical PyMongo find_one results.
    # ------------------------------------


    logger.info(f"✅ Usuario encontrado y listo para serializar: {email}")
    # Return the potentially modified dictionary
    # Pydantic will still validate against UserResponseModel,
    # but _id should now be a string, matching the 'id: str' field.
    return user_document


# Asegúrate de que este router esté incluido en tu aplicación FastAPI principal
# En tu archivo main.py o app.py:
# from .auth import router as auth_router # Ajusta la importación según tu estructura
# app.include_router(auth_router, prefix="/auth")
