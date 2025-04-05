from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from resemblyzer import preprocess_wav, VoiceEncoder
import numpy as np
import librosa
import io
import os
import logging
import time
import traceback
from config import (
    VOICE_SIMILARITY_THRESHOLD,
    ENVIRONMENT,
    IS_PRODUCTION
)
# Eliminar esta importación para evitar la circularidad
# from utils.auth_utils import get_current_user
from mongodb_client import MongoDBClient
from scipy.spatial.distance import cosine
from azure_storage import upload_voice_recording

# Configurar logging
logging.basicConfig(
    level=logging.INFO if IS_PRODUCTION else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Log del entorno actual
logger.info(f"Ejecutando en entorno: {ENVIRONMENT}")

router = APIRouter()
mongo_client = MongoDBClient()

# Crear una instancia global del codificador para reutilizarla
voice_encoder = None

def get_voice_encoder():
    """
    Retorna una instancia del codificador de voz, creándola si no existe.
    """
    global voice_encoder
    if voice_encoder is None:
        start_time = time.time()
        logger.info("🔄 Inicializando modelo de codificación de voz...")
        try:
            voice_encoder = VoiceEncoder()
            load_time = time.time() - start_time
            logger.info(f"✅ Modelo de voz cargado en {load_time:.2f} segundos")
        except Exception as e:
            logger.error(f"❌ Error al cargar el modelo de voz: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    return voice_encoder

# Inicializar el modelo de voz al arrancar
try:
    logger.info("🚀 Precargando modelo de codificación de voz...")
    get_voice_encoder()
except Exception as e:
    logger.error(f"❌ Error al precargar el modelo de voz: {str(e)}")

def extract_embedding(audio_path: str) -> np.ndarray:
    """
    Extrae el embedding de voz de un archivo de audio usando VoiceEncoder.
    """
    try:
        logger.info(f"Extrayendo embedding de {audio_path}")
        start_time = time.time()
        
        # Verificar que el archivo existe y no está vacío
        if not os.path.exists(audio_path):
            logger.error(f"El archivo {audio_path} no existe")
            return None
            
        if os.path.getsize(audio_path) == 0:
            logger.error(f"El archivo {audio_path} está vacío")
            return None
            
        # Verificar tamaño máximo (15MB)
        max_size = 15 * 1024 * 1024  # 15MB
        if os.path.getsize(audio_path) > max_size:
            logger.error(f"El archivo {audio_path} es demasiado grande: {os.path.getsize(audio_path)} bytes")
            return None
            
        # Verificar duración máxima (10 segundos)
        audio, sr = librosa.load(audio_path, sr=None)
        duration = len(audio) / sr
        if duration > 10:
            logger.warning(f"⚠️ Audio demasiado largo: {duration:.2f}s > 10s, se truncará")
            audio = audio[:int(10 * sr)]
            # Guardar audio truncado
            librosa.output.write_wav(audio_path, audio, sr)

        # Cargar y preprocesar el audio usando resemblyzer
        wav = preprocess_wav(audio_path)
        
        # Verificar que el audio no está vacío
        if len(wav) == 0:
            logger.error("No se pudo cargar el audio o el audio está vacío")
            return None
            
        # Obtener el codificador
        encoder = get_voice_encoder()
        if encoder is None:
            logger.error("No se pudo obtener el codificador de voz")
            return None
            
        # Extraer embedding usando resemblyzer
        embedding = encoder.embed_utterance(wav)
        
        process_time = time.time() - start_time
        logger.info(f"✅ Embedding extraído correctamente en {process_time:.2f}s. Tamaño: {len(embedding)}")
        return embedding.tolist()

    except Exception as e:
        logger.error(f"❌ Error al extraer embedding: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def compare_voices(embedding1, embedding2):
    """
    Compara dos embeddings de voz usando similitud del coseno.
    
    Args:
        embedding1: Primer embedding de voz
        embedding2: Segundo embedding de voz
        
    Returns:
        float: Similitud entre 0 y 1
    """
    try:
        logger.info("Comparando embeddings de voz")
        
        # Convertir a numpy arrays si son listas
        if isinstance(embedding1, list):
            embedding1 = np.array(embedding1)
        if isinstance(embedding2, list):
            embedding2 = np.array(embedding2)
            
        logger.info(f"Embedding 1 tipo: {type(embedding1)}, longitud: {len(embedding1)}")
        logger.info(f"Embedding 2 tipo: {type(embedding2)}, longitud: {len(embedding2)}")
        
        # Verificar que los embeddings no son nulos o vacíos
        if embedding1 is None or embedding2 is None or len(embedding1) == 0 or len(embedding2) == 0:
            logger.warning("Uno de los embeddings es nulo o vacío")
            return 0.0
            
        # Verificar que los embeddings no sean todos ceros
        if np.all(np.abs(embedding1) < 1e-10) or np.all(np.abs(embedding2) < 1e-10):
            logger.warning("Uno de los embeddings es prácticamente cero")
            return 0.0
        
        # Usar la función de scipy para calcular la distancia del coseno
        # cosine_distance = 1 - similarity, por lo que hacemos 1 - cosine_distance
        similarity = 1 - cosine(embedding1, embedding2)
        
        logger.info(f"Similitud calculada: {similarity}")
        
        # Asegurar que el resultado está entre 0 y 1
        similarity = max(0.0, min(1.0, similarity))
        
        return float(similarity)
        
    except Exception as e:
        logger.error(f"Error al comparar embeddings: {str(e)}")
        return 0.0
    
@router.post("/extract-embedding")
async def extract_voice_embedding(voice_recording: UploadFile = File(...)):
    """
    Extrae el embedding de un archivo de voz
    """
    try:
        logger.info("Extrayendo embedding de voz")
        
        # Guardar archivo temporalmente
        temp_file_path = f"temp_{voice_recording.filename}"
        with open(temp_file_path, "wb") as temp_file:
            content = await voice_recording.read()
            temp_file.write(content)
        
        # Extraer embedding
        embedding = extract_embedding(temp_file_path)
        
        # Eliminar archivo temporal
        os.remove(temp_file_path)
        
        return {"embedding": embedding}
        
    except Exception as e:
        logger.error(f"Error al extraer embedding: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error al procesar el archivo de voz"
        )

@router.post("/compare-voices")
async def compare_voice_samples(
    voice1: UploadFile = File(...),
    voice2: UploadFile = File(...)
):
    """
    Compara dos muestras de voz
    """
    try:
        logger.info("Comparando muestras de voz")
        
        # Procesar primera voz
        temp_path1 = f"temp_{voice1.filename}"
        with open(temp_path1, "wb") as temp_file:
            content = await voice1.read()
            temp_file.write(content)
        embedding1 = extract_embedding(temp_path1)
        
        # Procesar segunda voz
        temp_path2 = f"temp_{voice2.filename}"
        with open(temp_path2, "wb") as temp_file:
            content = await voice2.read()
            temp_file.write(content)
        embedding2 = extract_embedding(temp_path2)
        
        # Comparar embeddings
        similarity = compare_voices(embedding1, embedding2)
        
        # Limpiar archivos temporales
        os.remove(temp_path1)
        os.remove(temp_path2)
        
        return {"similarity": similarity}
        
    except Exception as e:
        logger.error(f"Error al comparar voces: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error al procesar los archivos de voz"
        )

@router.post("/register-voice")
async def register_voice(
    voice_recording: UploadFile = File(...),
    # No importamos directamente get_current_user
    current_user: dict = None
):
    """
    Registra una nueva muestra de voz para el usuario
    """
    try:
        # Si no se proporcionó el usuario, importamos y usamos get_current_user
        if current_user is None:
            # Importar localmente para evitar importación circular
            from utils.auth_utils import get_current_user
            from fastapi import Depends
            
            # Si estamos en una solicitud real, esto se resolverá correctamente
            current_user = Depends(get_current_user)
        
        logger.info(f"Registrando nueva voz para: {current_user['email']}")
        
        # Guardar archivo temporalmente
        temp_file_path = f"temp_{voice_recording.filename}"
        with open(temp_file_path, "wb") as temp_file:
            content = await voice_recording.read()
            temp_file.write(content)
        
        # Extraer embedding
        voice_embedding = extract_embedding(temp_file_path)
        
        # Subir a Azure Storage - llamado asíncrono con el email
        voice_url = await upload_voice_recording(temp_file_path, current_user["email"])
        
        if not voice_url:
            logger.error("❌ No se pudo subir el archivo de voz a Azure Storage")
            raise HTTPException(
                status_code=503,
                detail="Error al subir archivo de voz a Azure Storage"
            )
        
        # Eliminar archivo temporal
        os.remove(temp_file_path)
        
        # Actualizar en la base de datos
        success = mongo_client.update_user_voice(
            email=current_user["email"],
            voice_embedding=voice_embedding,
            voice_url=voice_url
        )
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Error al actualizar los datos de voz"
            )
        
        return {
            "message": "Voz registrada exitosamente",
            "voice_url": voice_url
        }
        
    except Exception as e:
        logger.error(f"Error al registrar voz: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error al procesar el archivo de voz"
        )

@router.post("/analyze", status_code=200)
async def analyze_voice(
    voice_recording: UploadFile = File(...),
    # Importar get_current_user localmente para evitar circularidad
    current_user: dict = None
):
    """
    Analiza una grabación de voz y devuelve su embedding.
    
    Args:
        voice_recording: Archivo de audio a analizar
        current_user: Usuario actual (opcional)
        
    Returns:
        dict: Información del análisis de voz
    """
    try:
        # Verificar si se requiere autenticación
        if current_user is None:
            # Importar localmente para evitar importación circular
            from utils.auth_utils import get_current_user
            from fastapi import Depends
            
            # Obtener el usuario actual si se requiere
            current_user = Depends(get_current_user)
        
        logger.info("Extrayendo embedding de voz")
        
        # Guardar archivo temporalmente
        temp_file_path = f"temp_{voice_recording.filename}"
        with open(temp_file_path, "wb") as temp_file:
            content = await voice_recording.read()
            temp_file.write(content)
        
        # Extraer embedding
        embedding = extract_embedding(temp_file_path)
        
        # Eliminar archivo temporal
        os.remove(temp_file_path)
        
        return {"embedding": embedding}
        
    except Exception as e:
        logger.error(f"Error al extraer embedding: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error al procesar el archivo de voz"
        ) 