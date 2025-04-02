from resemblyzer import preprocess_wav, VoiceEncoder
import numpy as np
import librosa
import io
import os
import logging
from config import VOICE_SIMILARITY_THRESHOLD

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('voice_processing.log')
    ]
)
logger = logging.getLogger(__name__)

def extract_voice_embedding(audio_file):
    """
    Extrae el embedding de voz usando Resemblyzer
    
    Args:
        audio_file: El archivo de audio a procesar
        
    Returns:
        numpy.ndarray: El embedding de voz
    """
    logger.info(f"Iniciando extracción de embedding para archivo: {audio_file}")
    try:
        # Verificar que el archivo existe
        if not os.path.exists(audio_file):
            logger.error(f"El archivo de audio no existe: {audio_file}")
            raise FileNotFoundError(f"El archivo de audio no existe: {audio_file}")
        
        # Cargar el audio
        logger.info("Cargando archivo de audio...")
        audio, sr = librosa.load(audio_file, sr=16000)
        logger.info(f"Audio cargado. Duración: {len(audio)/sr:.2f}s, Sample rate: {sr}Hz")
        
        # Preprocesar el audio
        logger.info("Preprocesando audio...")
        processed_audio = preprocess_wav(audio)
        logger.info("Audio preprocesado correctamente")
        
        # Crear el encoder
        logger.info("Inicializando encoder de voz...")
        encoder = VoiceEncoder()
        
        # Extraer el embedding
        logger.info("Extrayendo embedding...")
        embedding = encoder.embed_utterance(processed_audio)
        logger.info(f"Embedding extraído. Dimensión: {len(embedding)}")
        
        return embedding
        
    except Exception as e:
        logger.error(f"Error al procesar el audio: {str(e)}")
        raise

def compare_voice_embeddings(embedding1, embedding2, threshold=None):
    """
    Compara dos embeddings de voz
    
    Args:
        embedding1: Primer embedding
        embedding2: Segundo embedding
        threshold: Umbral de similitud (0-1), si es None usa el de la configuración
        
    Returns:
        float: Similitud entre los embeddings (0-1)
    """
    logger.info("Iniciando comparación de embeddings")
    try:
        # Usar el umbral proporcionado o el de la configuración
        threshold = threshold or VOICE_SIMILARITY_THRESHOLD
        logger.info(f"Umbral de similitud: {threshold}")
        
        # Verificar dimensiones
        if len(embedding1) != len(embedding2):
            logger.error(f"Dimensiones de embeddings no coinciden: {len(embedding1)} != {len(embedding2)}")
            raise ValueError("Los embeddings deben tener la misma dimensión")
        
        # Calcular similitud
        similarity = float(np.dot(embedding1, embedding2) / 
                         (np.linalg.norm(embedding1) * np.linalg.norm(embedding2)))
        
        logger.info(f"Similitud calculada: {similarity:.4f}")
        return similarity
        
    except Exception as e:
        logger.error(f"Error al comparar embeddings: {str(e)}")
        raise 