from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from resemblyzer import preprocess_wav, VoiceEncoder
import numpy as np
import librosa
import io
import os
import logging
import time
import traceback
import soundfile as sf
from config import (
    VOICE_SIMILARITY_THRESHOLD,
    ENVIRONMENT,
    IS_PRODUCTION
)
from mongodb_client import MongoDBClient
from scipy.spatial.distance import cosine
from azure_storage import upload_voice_recording
from pydub import AudioSegment
from pydub.silence import split_on_silence
import noisereduce as nr

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

# Comprobar si resemblyzer está disponible
try:
    from resemblyzer import preprocess_wav, VoiceEncoder
    RESEMBLYZER_AVAILABLE = True
    logger.info("✅ La biblioteca resemblyzer se ha importado correctamente")
except ImportError as e:
    logger.error(f"❌ La biblioteca resemblyzer no está instalada: {str(e)}")
    logger.error("❌ Para instalar: pip install resemblyzer==0.1.0")
    RESEMBLYZER_AVAILABLE = False
except Exception as e:
    logger.error(f"❌ Error al importar resemblyzer: {str(e)}")
    logger.error(traceback.format_exc())
    RESEMBLYZER_AVAILABLE = False

router = APIRouter()
mongo_client = MongoDBClient()

# Crear una instancia global del codificador para reutilizarla
voice_encoder = None

def get_voice_encoder():
    """
    Retorna una instancia del codificador de voz, creándola si no existe.
    
    Nota: Este código fue diseñado originalmente para resemblyzer<=0.1.0 
    que incluía el método segment_utterance. Las versiones más recientes
    podrían no tener esta función.
    """
    global voice_encoder
    
    # Si resemblyzer no está disponible, no intentar inicializar
    if not RESEMBLYZER_AVAILABLE:
        logger.error("❌ Resemblyzer no está disponible, no se puede inicializar el codificador")
        return None
        
    if voice_encoder is None:
        start_time = time.time()
        logger.error(f"⚠️ Modelo no inicializado, cargando por primera vez en {ENVIRONMENT}...")
        try:
            # Intentar obtener la versión de resemblyzer
            try:
                import pkg_resources
                resemblyzer_version = pkg_resources.get_distribution("resemblyzer").version
                logger.error(f"📦 Versión de resemblyzer: {resemblyzer_version}")
            except Exception as ve:
                logger.error(f"⚠️ No se pudo determinar la versión de resemblyzer: {str(ve)}")
                
            # Inicializar el codificador
            logger.error("🔄 Comenzando inicialización del modelo de voz...")
            voice_encoder = VoiceEncoder()
            
            # Verificar que el modelo realmente esté cargado haciendo una operación pequeña
            dummy_audio = np.zeros(16000)  # 1 segundo de silencio a 16kHz
            _ = voice_encoder.embed_utterance(dummy_audio)
            
            load_time = time.time() - start_time
            logger.error(f"✅ Modelo de voz cargado y verificado en {load_time:.2f} segundos")
            
            # Verificar si tiene el método segment_utterance
            if hasattr(voice_encoder, 'segment_utterance'):
                logger.error("✅ Método segment_utterance disponible")
            else:
                logger.error("⚠️ Método segment_utterance no disponible, se usará embed_utterance directamente")
                
        except Exception as e:
            logger.error(f"❌ Error al cargar el modelo de voz: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    else:
        logger.info("✅ Usando modelo ya cargado en memoria")
    
    return voice_encoder

# Inicializar el modelo de voz al arrancar - modo ligero para no bloquear el arranque
if RESEMBLYZER_AVAILABLE:
    try:
        logger.error("🚀 Configurando inicialización diferida del modelo de voz...")
        import threading
        
        # Esta función ejecutará la carga del modelo en segundo plano
        def load_model_in_background():
            try:
                logger.error("🧵 Iniciando carga del modelo en hilo secundario...")
                time.sleep(10)  # Esperar 10 segundos después del arranque para evitar problemas con healthcheck
                
                # Intentar cargar el modelo
                import pkg_resources
                try:
                    resemblyzer_version = pkg_resources.get_distribution("resemblyzer").version
                    logger.error(f"📦 Versión de resemblyzer: {resemblyzer_version}")
                except Exception as ve:
                    logger.error(f"⚠️ No se pudo determinar la versión de resemblyzer: {str(ve)}")
                
                # Cargar el modelo
                start_time = time.time()
                global voice_encoder
                voice_encoder = VoiceEncoder()
                
                # Verificar que el modelo realmente esté cargado con una operación pequeña
                dummy_audio = np.zeros(16000)  # 1 segundo de silencio a 16kHz
                _ = voice_encoder.embed_utterance(dummy_audio)
                
                load_time = time.time() - start_time
                logger.error(f"✅ Modelo de voz cargado en segundo plano en {load_time:.2f}s")
            except Exception as e:
                logger.error(f"❌ Error al cargar el modelo en segundo plano: {str(e)}")
                logger.error(traceback.format_exc())
        
        # Iniciar un hilo para cargar el modelo en segundo plano
        init_thread = threading.Thread(target=load_model_in_background)
        init_thread.daemon = True  # El hilo no bloqueará la salida de la aplicación
        init_thread.start()
        logger.error("🧵 Inicialización del modelo delegada a un hilo en segundo plano")
        
    except Exception as e:
        logger.error(f"❌ Error al configurar la carga en segundo plano: {str(e)}")
        logger.error(traceback.format_exc())
else:
    logger.error("⚠️ Resemblyzer no está disponible, no se precargará el modelo de voz")

def preprocess_audio(audio_path):
    """
    Preprocesa el audio para mejorar la calidad antes de la extracción del embedding:
    1. Elimina silencios
    2. Normaliza el volumen
    3. Reduce el ruido
    4. Estandariza la tasa de muestreo
    """
    try:
        logger.info(f"Preprocesando audio: {audio_path}")
        
        # Cargar audio
        audio, sr = librosa.load(audio_path, sr=None)
        
        # Convertir a mono si es estéreo
        if len(audio.shape) > 1:
            audio = librosa.to_mono(audio)
        
        # Estandarizar tasa de muestreo a 16000 Hz (óptimo para VoiceEncoder)
        if sr != 16000:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
            sr = 16000
        
        # Reducción de ruido
        audio_denoised = nr.reduce_noise(y=audio, sr=sr)
        
        # Normalizar volumen
        audio_normalized = librosa.util.normalize(audio_denoised)
        
        # Guardar audio preprocesado
        sf.write(audio_path, audio_normalized, sr)
        
        # Detectar y eliminar silencios usando pydub
        sound = AudioSegment.from_file(audio_path)
        chunks = split_on_silence(
            sound,
            min_silence_len=500,  # mínimo 500ms para considerar silencio
            silence_thresh=-40,   # umbral para detectar silencio
            keep_silence=100      # mantener 100ms al inicio y final
        )
        
        if chunks:
            # Combinar los chunks no silenciosos
            combined = chunks[0]
            for chunk in chunks[1:]:
                combined += chunk
                
            # Normalizar volumen nuevamente
            combined = combined.normalize()
            
            # Guardar audio procesado
            combined.export(audio_path, format="wav")
            
        logger.info(f"✅ Audio preprocesado correctamente")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al preprocesar audio: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def extract_embedding(audio_path: str) -> np.ndarray:
    """
    Extrae el embedding de voz de un archivo de audio usando VoiceEncoder.
    
    Si resemblyzer no está disponible, retorna None y genera un HTTPException.
    """
    # Verificar si resemblyzer está disponible
    if not RESEMBLYZER_AVAILABLE:
        logger.warning("⚠️ No se puede extraer embedding: resemblyzer no está disponible")
        raise HTTPException(
            status_code=503,
            detail="El servicio de procesamiento de voz no está disponible temporalmente. Por favor, intente más tarde."
        )
        
    try:
        logger.info(f"Extrayendo embedding de {audio_path}")
        start_time = time.time()
        
        # Verificar que el archivo existe y no está vacío
        if not os.path.exists(audio_path):
            logger.error(f"El archivo {audio_path} no existe")
            raise HTTPException(status_code=400, detail="El archivo de audio no existe")
            
        if os.path.getsize(audio_path) == 0:
            logger.error(f"El archivo {audio_path} está vacío")
            raise HTTPException(status_code=400, detail="El archivo de audio está vacío")
            
        # Verificar tamaño máximo (15MB)
        max_size = 15 * 1024 * 1024  # 15MB
        if os.path.getsize(audio_path) > max_size:
            logger.error(f"El archivo {audio_path} es demasiado grande: {os.path.getsize(audio_path)} bytes")
            raise HTTPException(status_code=400, detail="El archivo de audio excede el tamaño máximo permitido (15MB)")
         
        # Preprocesar el audio para mejorar calidad
        if not preprocess_audio(audio_path):
            logger.warning("⚠️ No se pudo preprocesar el audio, usando audio original")
          
        # Verificar formato y duración
        try:
            y, sr = librosa.load(audio_path, sr=None)
            duration = librosa.get_duration(y=y, sr=sr)
            logger.info(f"Duración del audio: {duration:.2f}s, Tasa de muestreo: {sr}Hz")
            
            # Verificar duración máxima (10 segundos)
            if duration > 10:
                logger.warning(f"⚠️ Audio demasiado largo: {duration:.2f}s > 10s, se truncará")
                audio = y[:int(10 * sr)]
                # Guardar audio truncado
                sf.write(audio_path, audio, sr)
            elif duration < 1.0:
                logger.warning(f"⚠️ Audio muy corto: {duration:.2f}s")
                raise HTTPException(status_code=400, detail="El audio es demasiado corto para procesarlo correctamente")
        except Exception as e:
            logger.error(f"Error al verificar el audio: {str(e)}")
            raise HTTPException(status_code=400, detail="El archivo de audio no es válido o está corrupto")
        
        try:
            # Cargar y preprocesar el audio usando resemblyzer
            wav = preprocess_wav(audio_path)
        except Exception as e:
            logger.error(f"❌ Error al preprocesar el audio con resemblyzer: {str(e)}")
            raise HTTPException(
                status_code=400, 
                detail="No se pudo procesar el audio. Asegúrese de que sea un archivo WAV válido."
            )
        
        # Verificar que el audio no está vacío
        if len(wav) == 0:
            logger.error("No se pudo cargar el audio o el audio está vacío")
            raise HTTPException(status_code=400, detail="El archivo de audio está vacío después del preprocesamiento")
            
        # Obtener el codificador
        encoder = get_voice_encoder()
        if encoder is None:
            logger.error("No se pudo obtener el codificador de voz")
            raise HTTPException(
                status_code=503,
                detail="El servicio de procesamiento de voz no está disponible temporalmente. Por favor, intente más tarde."
            )
            
        # Extraer embedding usando resemblyzer
        try:
            # Intentar usar segmentación si está disponible
            if hasattr(encoder, 'segment_utterance'):
                logger.info("Usando método segment_utterance")
                segments = encoder.segment_utterance(wav, rate=1.3)  # Mayor rate = más segmentos
                if len(segments) == 0:
                    logger.warning("⚠️ No se pudieron extraer segmentos, usando todo el audio")
                    embedding = encoder.embed_utterance(wav)
                else:
                    embeddings = [encoder.embed_utterance(segment) for segment in segments]
                    embedding = np.mean(embeddings, axis=0)
            else:
                # Si el método segment_utterance no está disponible, usar directamente embed_utterance
                logger.info("Método segment_utterance no disponible, usando embed_utterance directamente")
                embedding = encoder.embed_utterance(wav)
        except Exception as e:
            logger.error(f"❌ Error al extraer embedding con segmentación: {str(e)}")
            # Intentar el método básico como fallback
            try:
                logger.info("Intentando método alternativo embed_utterance")
                embedding = encoder.embed_utterance(wav)
                logger.info("✅ Embedding extraído usando método alternativo")
            except Exception as e2:
                logger.error(f"❌ Error al extraer embedding con método alternativo: {str(e2)}")
                return None
        
        # Verificar que el embedding sea válido
        if embedding is None:
            logger.error("❌ Se obtuvo un embedding nulo")
            return None
            
        if not isinstance(embedding, (np.ndarray, list)):
            logger.error(f"❌ El embedding no es del tipo esperado: {type(embedding)}")
            return None
            
        process_time = time.time() - start_time
        logger.info(f"✅ Embedding extraído correctamente en {process_time:.2f}s. Tamaño: {len(embedding)}")
        
        # Convertir a lista si es un ndarray
        if isinstance(embedding, np.ndarray):
            return embedding.tolist()
        return embedding

    except Exception as e:
        logger.error(f"❌ Error al extraer embedding: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def compare_voices(embedding1, embedding2, threshold=VOICE_SIMILARITY_THRESHOLD):
    """
    Compara dos embeddings de voz usando similitud del coseno.
    
    Args:
        embedding1: Primer embedding de voz
        embedding2: Segundo embedding de voz
        threshold: Umbral de similitud para considerar que son la misma voz
        
    Returns:
        dict: Resultado de la comparación con similitud y decisión
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
            return {"similarity": 0.0, "match": False}
            
        # Verificar que los embeddings no sean todos ceros
        if np.all(np.abs(embedding1) < 1e-10) or np.all(np.abs(embedding2) < 1e-10):
            logger.warning("Uno de los embeddings es prácticamente cero")
            return {"similarity": 0.0, "match": False}
        
        # Usar la función de scipy para calcular la distancia del coseno
        # cosine_distance = 1 - similarity, por lo que hacemos 1 - cosine_distance
        similarity = 1 - cosine(embedding1, embedding2)
        
        logger.info(f"Similitud calculada: {similarity}")
        
        # Asegurar que el resultado está entre 0 y 1
        similarity = max(0.0, min(1.0, similarity))
        
        # Determinar si hay coincidencia basado en el umbral
        match = similarity >= threshold
        
        return {
            "similarity": float(similarity),
            "match": match,
            "threshold": threshold
        }
        
    except Exception as e:
        logger.error(f"Error al comparar embeddings: {str(e)}")
        return {"similarity": 0.0, "match": False}

def store_multiple_embeddings(user_email, voice_recording_path, voice_url):
    """
    Genera y almacena múltiples embeddings de un mismo audio para mejorar
    la robustez del sistema de reconocimiento.
    """
    temp_files = []
    
    try:
        logger.info(f"Generando múltiples embeddings para {user_email}")
        
        # Verificar si el archivo original existe
        if not os.path.exists(voice_recording_path):
            logger.error(f"❌ El archivo original {voice_recording_path} no existe")
            return False
        
        # Cargar audio
        try:
            y, sr = librosa.load(voice_recording_path, sr=None)
        except Exception as e:
            logger.error(f"❌ Error al cargar el audio: {str(e)}")
            return False
        
        # Generar variantes con pequeñas perturbaciones para aumentar datos
        embeddings = []
        
        # No necesitamos volver a agregar el embedding original
        # ya que se agregó en el paso anterior
        
        # Variante 1: Ligero cambio de velocidad (+3%)
        temp_path1 = f"temp_stretch_{os.path.basename(voice_recording_path)}"
        temp_files.append(temp_path1)
        try:
            y_stretch = librosa.effects.time_stretch(y, rate=1.03)
            sf.write(temp_path1, y_stretch, sr)
            embedding1 = extract_embedding(temp_path1)
            if embedding1:
                embeddings.append(embedding1)
                logger.info("✅ Generado embedding con cambio de velocidad")
            else:
                logger.warning("⚠️ No se pudo extraer embedding con cambio de velocidad")
        except Exception as e:
            logger.error(f"❌ Error al generar variante de velocidad: {str(e)}")
        
        # Variante 2: Ligero cambio de tono (-1 semitono)
        temp_path2 = f"temp_pitch_{os.path.basename(voice_recording_path)}"
        temp_files.append(temp_path2)
        try:
            y_pitch = librosa.effects.pitch_shift(y, sr=sr, n_steps=-1)
            sf.write(temp_path2, y_pitch, sr)
            embedding2 = extract_embedding(temp_path2)
            if embedding2:
                embeddings.append(embedding2)
                logger.info("✅ Generado embedding con cambio de tono")
            else:
                logger.warning("⚠️ No se pudo extraer embedding con cambio de tono")
        except Exception as e:
            logger.error(f"❌ Error al generar variante de tono: {str(e)}")
        
        # Si generamos nuevos embeddings, actualizar la base de datos
        if embeddings:
            # Obtener embeddings existentes
            user_data = mongo_client.get_user_voice_data(user_email)
            
            if user_data and 'voice_embeddings' in user_data:
                # Combinar embeddings existentes con los nuevos
                existing_embeddings = user_data['voice_embeddings']
                combined_embeddings = existing_embeddings + embeddings
                logger.info(f"Combinando {len(existing_embeddings)} embeddings existentes con {len(embeddings)} nuevos")
            else:
                # Solo usar los nuevos embeddings
                combined_embeddings = embeddings
            
            # Actualizar en la base de datos con todos los embeddings
            success = mongo_client.update_user_voice_gallery(
                email=user_email,
                voice_embeddings=combined_embeddings,
                voice_url=voice_url
            )
            
            logger.info(f"✅ Galería de voz actualizada para {user_email} con {len(combined_embeddings)} embeddings totales")
            return success
        else:
            logger.info("⚠️ No se generaron embeddings adicionales")
            return True  # Ya se guardó el embedding inicial, así que no es un error
            
    except Exception as e:
        logger.error(f"❌ Error al generar múltiples embeddings: {str(e)}")
        return False
    finally:
        # Limpiar todos los archivos temporales
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.debug(f"🧹 Archivo temporal eliminado: {temp_file}")
                except Exception as e:
                    logger.error(f"❌ Error al eliminar archivo temporal {temp_file}: {str(e)}")
        
        # Eliminar archivo temporal original
        if os.path.exists(voice_recording_path):
            try:
                os.remove(voice_recording_path)
                logger.debug(f"🧹 Archivo original eliminado: {voice_recording_path}")
            except Exception as e:
                logger.error(f"❌ Error al eliminar archivo original {voice_recording_path}: {str(e)}")

@router.post("/extract-embedding")
async def extract_voice_embedding(voice_recording: UploadFile = File(...)):
    """
    Extrae el embedding de un archivo de voz
    """
    # Verificar si resemblyzer está disponible
    if not RESEMBLYZER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="El servicio de análisis de voz no está disponible. Instale resemblyzer==0.1.0."
        )
        
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
    voice2: UploadFile = File(...),
    threshold: float = None
):
    """
    Compara dos muestras de voz
    """
    # Verificar si resemblyzer está disponible
    if not RESEMBLYZER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="El servicio de comparación de voz no está disponible. Instale resemblyzer==0.1.0."
        )
        
    try:
        logger.info("Comparando muestras de voz")
        
        # Usar umbral personalizado o el predeterminado
        compare_threshold = threshold if threshold is not None else VOICE_SIMILARITY_THRESHOLD
        
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
        result = compare_voices(embedding1, embedding2, compare_threshold)
        
        # Limpiar archivos temporales
        os.remove(temp_path1)
        os.remove(temp_path2)
        
        return result
        
    except Exception as e:
        logger.error(f"Error al comparar voces: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error al procesar los archivos de voz"
        )

@router.post("/register-voice")
async def register_voice(
    voice_recording: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    current_user: dict = None
):
    """
    Registra una nueva muestra de voz para el usuario
    """
    # Verificar si resemblyzer está disponible
    if not RESEMBLYZER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="El servicio de registro de voz no está disponible. Instale resemblyzer==0.1.0."
        )
        
    temp_file_path = None
    
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
            if not content:
                logger.error("❌ El archivo de voz está vacío")
                raise HTTPException(
                    status_code=400,
                    detail="El archivo de voz está vacío"
                )
            temp_file.write(content)
            logger.info(f"💾 Archivo de voz guardado temporalmente: {temp_file_path}")
        
        # Preprocesar audio para mejorar calidad
        preprocess_audio(temp_file_path)
        
        # Extraer embedding principal
        voice_embedding = extract_embedding(temp_file_path)
        
        if voice_embedding is None:
            logger.error("❌ No se pudo extraer un embedding válido del audio")
            raise HTTPException(
                status_code=400,
                detail="No se pudo extraer un embedding válido del audio. Intente grabar nuevamente con mejor calidad."
            )
        
        # Subir a Azure Storage - llamado asíncrono con el email
        voice_url = await upload_voice_recording(temp_file_path, current_user["email"])
        
        if not voice_url:
            logger.error("❌ No se pudo subir el archivo de voz a Azure Storage")
            raise HTTPException(
                status_code=503,
                detail="Error al subir archivo de voz a Azure Storage"
            )
        
        # Generar y almacenar múltiples embeddings en segundo plano
        if background_tasks:
            # Registrar el embedding inicial de inmediato, luego se enriquecerá con variantes
            # Esto garantiza que haya al menos un embedding guardado aunque falle el proceso en segundo plano
            embeddings_iniciales = [voice_embedding]
            
            # Actualizar con el embedding inicial
            initial_success = mongo_client.update_user_voice_gallery(
                email=current_user["email"],
                voice_embeddings=embeddings_iniciales,
                voice_url=voice_url
            )
            
            if not initial_success:
                logger.error("❌ No se pudo guardar el embedding inicial")
                raise HTTPException(
                    status_code=500,
                    detail="Error al guardar el embedding de voz inicial"
                )
            
            logger.info(f"✅ Embedding inicial guardado para {current_user['email']}")
            
            # Ahora agregar la tarea en segundo plano para generar más variantes
            background_tasks.add_task(
                store_multiple_embeddings,
                current_user["email"],
                temp_file_path,
                voice_url
            )
            
            # Nota: No eliminamos el archivo temporal aquí, lo hará store_multiple_embeddings
            temp_file_path = None  # Evitar que se elimine en el bloque finally
            
            return {
                "message": "Voz registrada exitosamente. Optimizando reconocimiento en segundo plano.",
                "voice_url": voice_url
            }
        else:
            # Si no hay tareas en segundo plano, crear galería con un solo embedding
            embeddings = [voice_embedding]
            
            # Actualizar con una galería de embeddings (aunque solo tenga uno)
            success = mongo_client.update_user_voice_gallery(
                email=current_user["email"],
                voice_embeddings=embeddings,
                voice_url=voice_url
            )
            
            # Eliminar archivo temporal
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                temp_file_path = None
                logger.info("🧹 Archivo temporal eliminado")
            
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
    finally:
        # Asegurarnos de que el archivo temporal se elimine si hubo errores
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info("🧹 Archivo temporal eliminado en finally")
            except Exception as cleanup_error:
                logger.error(f"❌ Error al eliminar archivo temporal: {str(cleanup_error)}")

@router.post("/verify-voice")
async def verify_voice(
    voice_recording: UploadFile = File(...),
    email: str = None,
    current_user: dict = None
):
    """
    Verifica la identidad de un usuario comparando su voz con el registro.
    """
    # Verificar si resemblyzer está disponible
    if not RESEMBLYZER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="El servicio de verificación de voz no está disponible. Instale resemblyzer==0.1.0."
        )
        
    try:
        # Determinar el email a verificar
        user_email = None
        if email:
            user_email = email
        elif current_user:
            user_email = current_user['email']
        else:
            # Importar localmente para evitar importación circular
            from utils.auth_utils import get_current_user
            from fastapi import Depends
            
            current_user = Depends(get_current_user)
            user_email = current_user['email']
            
        if not user_email:
            raise HTTPException(
                status_code=400,
                detail="Se requiere un email para verificar la voz"
            )
            
        logger.info(f"Verificando voz para {user_email}")
        
        # Guardar archivo temporalmente
        temp_file_path = f"temp_{voice_recording.filename}"
        with open(temp_file_path, "wb") as temp_file:
            content = await voice_recording.read()
            temp_file.write(content)
            
        # Preprocesar y extraer embedding
        preprocess_audio(temp_file_path)
        input_embedding = extract_embedding(temp_file_path)
        
        if input_embedding is None:
            os.remove(temp_file_path)
            raise HTTPException(
                status_code=400,
                detail="No se pudo procesar el audio. Intente nuevamente en un entorno más silencioso."
            )
            
        # Obtener embeddings del usuario desde MongoDB
        user_data = mongo_client.get_user_voice_data(user_email)
        
        if not user_data or (not user_data.get('voice_embeddings') and not user_data.get('voice_embedding')):
            os.remove(temp_file_path)
            raise HTTPException(
                status_code=404,
                detail="No se encontró ningún registro de voz para el usuario"
            )
            
        # Verificar contra múltiples embeddings y tomar el mejor resultado
        best_similarity = 0
        is_match = False
        
        for stored_embedding in user_data.get('voice_embeddings', []):
            result = compare_voices(input_embedding, stored_embedding)
            if result["similarity"] > best_similarity:
                best_similarity = result["similarity"]
                is_match = result["match"]
                
        # Si no hay galería, verificar con el embedding principal
        if not user_data.get('voice_embeddings') and user_data.get('voice_embedding'):
            result = compare_voices(input_embedding, user_data['voice_embedding'])
            best_similarity = result["similarity"]
            is_match = result["match"]
            
        # Eliminar archivo temporal
        os.remove(temp_file_path)
        
        return {
            "similarity": best_similarity,
            "match": is_match,
            "threshold": VOICE_SIMILARITY_THRESHOLD
        }
        
    except Exception as e:
        logger.error(f"Error al verificar voz: {str(e)}")
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
    # Verificar si resemblyzer está disponible
    if not RESEMBLYZER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="El servicio de análisis de voz no está disponible. Instale resemblyzer==0.1.0."
        )
        
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
            
        # Preprocesar audio
        preprocess_audio(temp_file_path)
        
        # Extraer embedding
        embedding = extract_embedding(temp_file_path)
        
        # Analizar calidad del audio
        audio, sr = librosa.load(temp_file_path, sr=None)
        
        # Calcular relación señal-ruido (SNR)
        signal_power = np.mean(audio**2)
        noise_sample = audio[:int(0.1*sr)]  # Asumir que los primeros 100ms son ruido
        noise_power = np.mean(noise_sample**2)
        snr = 10 * np.log10(signal_power/noise_power) if noise_power > 0 else 100
        
        # Eliminar archivo temporal
        os.remove(temp_file_path)
        
        quality_assessment = "buena"
        recommendations = []
        
        if snr < 15:
            quality_assessment = "baja"
            recommendations.append("Grabar en un entorno más silencioso")
            
        if len(audio) / sr < 2:
            quality_assessment = "baja"
            recommendations.append("La grabación es demasiado corta, hablar durante al menos 2 segundos")
            
        return {
            "embedding": embedding,
            "audio_quality": {
                "assessment": quality_assessment,
                "snr": float(snr),
                "duration": float(len(audio) / sr),
                "recommendations": recommendations
            }
        }
        
    except Exception as e:
        logger.error(f"Error al extraer embedding: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error al procesar el archivo de voz"
        )

@router.get("/warmup")
async def warmup():
    """
    Endpoint para precalentar el modelo de voz.
    Útil para forzar la carga del modelo antes de usarlo.
    """
    if not RESEMBLYZER_AVAILABLE:
        return {
            "status": "error",
            "message": "Resemblyzer no está disponible",
            "model_loaded": False
        }
    
    try:
        start_time = time.time()
        logger.error("🔥 Iniciando warmup del modelo de voz...")
        
        encoder = get_voice_encoder()
        if encoder is None:
            logger.error("❌ No se pudo obtener el codificador de voz")
            return {
                "status": "error",
                "message": "No se pudo cargar el modelo de voz",
                "model_loaded": False
            }
        
        # Verificar que el modelo esté realmente cargado con una operación pequeña
        logger.error("🔄 Realizando operación de prueba en el modelo...")
        dummy_audio = np.zeros(16000)  # 1 segundo de silencio a 16kHz
        embedding = encoder.embed_utterance(dummy_audio)
        
        # Verificar el resultado
        if embedding is None or len(embedding) == 0:
            logger.error("❌ El modelo devolvió un embedding vacío")
            return {
                "status": "error",
                "message": "El modelo devolvió un embedding vacío",
                "model_loaded": False
            }
        
        process_time = time.time() - start_time
        logger.error(f"✅ Warmup completado exitosamente en {process_time:.2f}s")
        
        return {
            "status": "success",
            "message": f"Modelo precalentado correctamente en {process_time:.2f} segundos",
            "model_loaded": True
        }
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"❌ Error en el warmup: {str(e)}")
        logger.error(traceback.format_exc())
        
        return {
            "status": "error",
            "message": f"Error al precalentar el modelo: {str(e)}",
            "model_loaded": False,
            "time_elapsed": f"{process_time:.2f}s"
        }