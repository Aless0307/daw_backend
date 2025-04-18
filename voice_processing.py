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

# Silenciar los logs específicos de Numba y otros módulos ruidosos
for noisy_logger in ['numba', 'numba.core', 'numba.core.byteflow', 'matplotlib', 'PIL']:
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

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
        logger.info(f"⚠️ Modelo no inicializado, cargando por primera vez en {ENVIRONMENT}...")
        try:
            # Intentar obtener la versión de resemblyzer
            try:
                import pkg_resources
                resemblyzer_version = pkg_resources.get_distribution("resemblyzer").version
                logger.info(f"📦 Versión de resemblyzer: {resemblyzer_version}")
            except Exception as ve:
                logger.warning(f"⚠️ No se pudo determinar la versión de resemblyzer: {str(ve)}")
                
            # Inicializar el codificador
            logger.info("🔄 Comenzando inicialización del modelo de voz...")
            voice_encoder = VoiceEncoder()
            
            # Verificar que el modelo realmente esté cargado haciendo una operación pequeña
            dummy_audio = np.zeros(16000)  # 1 segundo de silencio a 16kHz
            _ = voice_encoder.embed_utterance(dummy_audio)
            
            load_time = time.time() - start_time
            logger.info(f"✅ Modelo de voz cargado y verificado en {load_time:.2f} segundos")
            
            # Verificar si tiene el método segment_utterance
            if hasattr(voice_encoder, 'segment_utterance'):
                logger.info("✅ Método segment_utterance disponible")
            else:
                logger.warning("⚠️ Método segment_utterance no disponible, se usará embed_utterance directamente")
                
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
                logger.info("🧵 Iniciando carga del modelo en hilo secundario...")
                time.sleep(10)  # Esperar 10 segundos después del arranque para evitar problemas con healthcheck
                
                # Intentar cargar el modelo
                import pkg_resources
                try:
                    resemblyzer_version = pkg_resources.get_distribution("resemblyzer").version
                    logger.info(f"📦 Versión de resemblyzer: {resemblyzer_version}")
                except Exception as ve:
                    logger.warning(f"⚠️ No se pudo determinar la versión de resemblyzer: {str(ve)}")
                
                # Cargar el modelo
                start_time = time.time()
                global voice_encoder
                voice_encoder = VoiceEncoder()
                
                # Verificar que el modelo realmente esté cargado con una operación pequeña
                dummy_audio = np.zeros(16000)  # 1 segundo de silencio a 16kHz
                _ = voice_encoder.embed_utterance(dummy_audio)
                
                load_time = time.time() - start_time
                logger.info(f"✅ Modelo de voz cargado en segundo plano en {load_time:.2f}s")
            except Exception as e:
                logger.error(f"❌ Error al cargar el modelo en segundo plano: {str(e)}")
                logger.error(traceback.format_exc())
        
        # Iniciar un hilo para cargar el modelo en segundo plano
        init_thread = threading.Thread(target=load_model_in_background)
        init_thread.daemon = True  # El hilo no bloqueará la salida de la aplicación
        init_thread.start()
        logger.info("🧵 Inicialización del modelo delegada a un hilo en segundo plano")
        
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
        logger.info(f"🔍 INICIO PREPROCESAMIENTO AUDIO: {audio_path}")
        
        # Verificar que el archivo existe
        if not os.path.exists(audio_path):
            logger.error(f"❌ El archivo {audio_path} no existe")
            return False
            
        # Verificar tamaño del archivo
        file_size = os.path.getsize(audio_path)
        logger.info(f"📊 Tamaño del archivo: {file_size/1024:.2f} KB")
        
        if file_size == 0:
            logger.error(f"❌ El archivo {audio_path} está vacío")
            return False
        
        # 1. Cargar audio
        logger.info(f"🔊 Cargando audio con librosa...")
        audio, sr = librosa.load(audio_path, sr=None)
        
        logger.info(f"📊 Audio cargado: duración={len(audio)/sr:.2f}s, sr={sr}Hz, forma={audio.shape}, tipo={audio.dtype}")
        
        # Verificar si hay datos de audio
        if len(audio) == 0:
            logger.error(f"❌ El archivo de audio está vacío después de cargarlo")
            return False
            
        # Analizar niveles de audio detallados
        audio_abs = np.abs(audio)
        audio_max = np.max(audio_abs)
        audio_mean = np.mean(audio_abs)
        audio_std = np.std(audio_abs)
        audio_median = np.median(audio_abs)
        audio_percentile_25 = np.percentile(audio_abs, 25)
        audio_percentile_75 = np.percentile(audio_abs, 75)
        
        logger.info(f"📊 ANÁLISIS DETALLADO DE AUDIO:")
        logger.info(f"📊 - Máximo: {audio_max:.6f}")
        logger.info(f"📊 - Promedio: {audio_mean:.6f}")
        logger.info(f"📊 - Mediana: {audio_median:.6f}")
        logger.info(f"📊 - Desviación estándar: {audio_std:.6f}")
        logger.info(f"📊 - Percentil 25%: {audio_percentile_25:.6f}")
        logger.info(f"📊 - Percentil 75%: {audio_percentile_75:.6f}")
        
        # Analizar silencio - dividir el audio en segmentos y mostrar la energía de cada uno
        segment_duration = 0.1  # 100ms por segmento
        segment_samples = int(segment_duration * sr)
        num_segments = len(audio) // segment_samples
        
        logger.info(f"📊 ANÁLISIS DE ENERGÍA POR SEGMENTOS (cada {segment_duration}s):")
        low_energy_segments = 0
        high_energy_segments = 0
        
        segment_energies = []
        for i in range(num_segments):
            start = i * segment_samples
            end = start + segment_samples
            segment = audio[start:end]
            energy = np.mean(np.square(segment))
            segment_energies.append(energy)
            
            if i < 10 or i > num_segments - 5:  # Mostrar los primeros y últimos segmentos
                logger.info(f"📊 - Segmento {i+1}/{num_segments}: energía={energy:.6f}")
            elif i == 10:
                logger.info(f"📊 - ... ({num_segments-15} segmentos más) ...")
                
            if energy < 0.0001:  # Umbral arbitrario para "silencio"
                low_energy_segments += 1
            else:
                high_energy_segments += 1
        
        if len(segment_energies) > 0:
            energy_mean = np.mean(segment_energies)
            energy_std = np.std(segment_energies)
            energy_max = np.max(segment_energies)
            logger.info(f"📊 Energía media de segmentos: {energy_mean:.6f}")
            logger.info(f"📊 Desviación estándar de energía: {energy_std:.6f}")
            logger.info(f"📊 Energía máxima: {energy_max:.6f}")
            logger.info(f"📊 Segmentos de baja energía: {low_energy_segments}/{num_segments} ({low_energy_segments/num_segments*100:.1f}%)")
        
        if audio_max < 0.01:
            logger.warning(f"⚠️ Nivel de audio muy bajo: máximo={audio_max:.6f}")
            logger.warning(f"⚠️ Es posible que este audio no contenga voz audible")
        
        # 2. Convertir a mono si es estéreo
        if len(audio.shape) > 1:
            logger.info(f"🔊 Convirtiendo audio estéreo a mono...")
            audio = librosa.to_mono(audio)
            logger.info(f"✅ Audio convertido a mono: {audio.shape}")
        
        # 3. Estandarizar tasa de muestreo a 16000 Hz (óptimo para VoiceEncoder)
        if sr != 16000:
            logger.info(f"🔊 Remuestreando audio de {sr}Hz a 16000Hz...")
            audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
            sr = 16000
            logger.info(f"✅ Audio remuestreado: duración={len(audio)/sr:.2f}s")
        
        # 4. Guardar una copia del audio original antes del procesamiento
        orig_path = audio_path + ".original.wav"
        logger.info(f"💾 Guardando copia del audio original en {orig_path}...")
        sf.write(orig_path, audio, sr)
        logger.info(f"✅ Copia original guardada")
        
        # 5. Reducción de ruido
        logger.info(f"🔊 Aplicando reducción de ruido...")
        try:
            audio_denoised = nr.reduce_noise(y=audio, sr=sr)
            logger.info(f"✅ Reducción de ruido aplicada")
            
            # Verificar si la reducción de ruido fue efectiva
            if np.array_equal(audio, audio_denoised):
                logger.warning("⚠️ La reducción de ruido no modificó el audio")
            else:
                # Analizar niveles después de reducción de ruido
                audio_dn_max = np.max(np.abs(audio_denoised))
                audio_dn_mean = np.mean(np.abs(audio_denoised))
                audio_dn_median = np.median(np.abs(audio_denoised))
                logger.info(f"📊 Audio post-reducción: máximo={audio_dn_max:.6f}, promedio={audio_dn_mean:.6f}, mediana={audio_dn_median:.6f}")
                
                # Calcular diferencia
                mean_change = abs(audio_dn_mean - audio_mean) / audio_mean * 100 if audio_mean > 0 else 0
                logger.info(f"📊 Cambio por reducción de ruido: {mean_change:.2f}%")
        except Exception as e:
            logger.error(f"❌ Error en reducción de ruido: {str(e)}")
            logger.warning("⚠️ Continuando sin reducción de ruido")
            audio_denoised = audio
        
        # 6. Normalizar volumen
        logger.info(f"🔊 Normalizando volumen...")
        try:
            audio_normalized = librosa.util.normalize(audio_denoised)
            logger.info(f"✅ Volumen normalizado")
            
            # Analizar niveles después de normalización
            audio_norm_max = np.max(np.abs(audio_normalized))
            audio_norm_mean = np.mean(np.abs(audio_normalized))
            audio_norm_median = np.median(np.abs(audio_normalized))
            logger.info(f"📊 Audio normalizado: máximo={audio_norm_max:.6f}, promedio={audio_norm_mean:.6f}, mediana={audio_norm_median:.6f}")
        except Exception as e:
            logger.error(f"❌ Error en normalización: {str(e)}")
            logger.warning("⚠️ Continuando sin normalización")
            audio_normalized = audio_denoised
        
        # 7. Guardar audio preprocesado (antes de eliminar silencio)
        preprocessed_path = audio_path + ".preprocessed.wav"
        logger.info(f"💾 Guardando audio preprocesado en {preprocessed_path}...")
        sf.write(preprocessed_path, audio_normalized, sr)
        logger.info(f"✅ Audio preprocesado guardado")
        
        # 8. Guardar audio intermedio para inspección
        sf.write(audio_path, audio_normalized, sr)
        
        # 9. Detectar y eliminar silencios usando pydub
        logger.info(f"🔊 Iniciando detección de silencio...")
        try:
            sound = AudioSegment.from_file(audio_path)
            logger.info(f"📊 Audio cargado en pydub: duración={sound.duration_seconds:.2f}s, canales={sound.channels}, tasa={sound.frame_rate}Hz, dBFS={sound.dBFS:.2f}dB")
            
            # Parámetros de detección de silencio - AJUSTADOS para mejor detección
            min_silence_len = 300  # ms (reducido para detectar silencios más cortos)
            silence_thresh = -35   # dB (aumentado para ser menos sensible al ruido de fondo)
            keep_silence = 50      # ms (reducido para recortar más silencio)
            
            # Probar diferentes umbrales para identificar el mejor
            logger.info(f"🔇 PRUEBA MULTI-UMBRAL DE SILENCIO:")
            for test_thresh in [-45, -40, -35, -30, -25]:
                test_chunks = split_on_silence(
                    sound,
                    min_silence_len=min_silence_len,
                    silence_thresh=test_thresh,
                    keep_silence=keep_silence
                )
                logger.info(f"📊 Umbral {test_thresh}dB: encontrados {len(test_chunks)} segmentos de voz")
            
            logger.info(f"🔇 USANDO PARÁMETROS FINALES: min_silence_len={min_silence_len}ms, silence_thresh={silence_thresh}dB, keep_silence={keep_silence}ms")
            
            # Proceso de división en chunks no silenciosos
            chunks = split_on_silence(
                sound,
                min_silence_len=min_silence_len,
                silence_thresh=silence_thresh,
                keep_silence=keep_silence
            )
            
            logger.info(f"🔊 Detección completa: se encontraron {len(chunks)} segmentos de voz")
            
            # Si no se detectaron chunks, intentar con un umbral más alto
            if len(chunks) == 0:
                logger.warning("⚠️ No se detectaron segmentos de voz con el umbral actual, probando con un umbral más alto")
                chunks = split_on_silence(
                    sound,
                    min_silence_len=min_silence_len,
                    silence_thresh=-25,  # Umbral más alto (menos negativo) para detectar más audio
                    keep_silence=keep_silence
                )
                logger.info(f"🔊 Nueva detección: se encontraron {len(chunks)} segmentos de voz")
            
            # Detallar cada chunk encontrado
            if chunks:
                for i, chunk in enumerate(chunks):
                    chunk_db = chunk.dBFS
                    chunk_dur = chunk.duration_seconds
                    logger.info(f"📊 Chunk #{i+1}: duración={chunk_dur:.3f}s, nivel={chunk_db:.2f}dB")
                
                # 10. Combinar los chunks no silenciosos
                logger.info(f"🔊 Combinando {len(chunks)} segmentos de audio...")
                combined = chunks[0]
                for chunk in chunks[1:]:
                    combined += chunk
                    
                # 11. Normalizar volumen nuevamente
                logger.info(f"🔊 Normalizando volumen final...")
                combined = combined.normalize()
                
                # 12. Guardar audio procesado
                final_path = audio_path + ".final.wav"
                logger.info(f"💾 Guardando copia del audio final en {final_path}")
                combined.export(final_path, format="wav")
                
                # 13. Guardar audio procesado en la ruta original
                logger.info(f"💾 Guardando audio procesado en {audio_path}")
                combined.export(audio_path, format="wav")
                
                # Verificar el resultado
                final_duration = combined.duration_seconds
                logger.info(f"📊 Audio final: duración={final_duration:.2f}s, nivel={combined.dBFS:.2f}dB")
                
                # Verificar que la duración no sea demasiado corta
                if final_duration < 0.5:
                    logger.warning(f"⚠️ Audio final muy corto: {final_duration:.2f}s, posible error en detección de silencio")
                    
                    # Restaurar audio preprocesado si el audio final es demasiado corto
                    logger.info("🔄 Restaurando audio preprocesado debido a duración insuficiente")
                    sound = AudioSegment.from_file(preprocessed_path)
                    sound.export(audio_path, format="wav")
                    
                    logger.info(f"✅ Audio restaurado: duración={sound.duration_seconds:.2f}s")
                    
            else:
                logger.warning("⚠️ No se detectaron segmentos de voz, usando audio completo")
                # Si no hay chunks, usar el audio preprocesado completo
                sound = AudioSegment.from_file(preprocessed_path)
                sound.export(audio_path, format="wav")
                
            logger.info(f"✅ Procesamiento de silencio completado correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error en detección de silencio: {str(e)}")
            logger.error(traceback.format_exc())
            logger.warning("⚠️ Continuando con el audio preprocesado sin eliminar silencios")
            # Intentar usar el archivo preprocesado como fallback
            try:
                if os.path.exists(preprocessed_path):
                    sound = AudioSegment.from_file(preprocessed_path)
                    sound.export(audio_path, format="wav")
                    logger.info("✅ Se usó el audio preprocesado como fallback")
            except Exception as e2:
                logger.error(f"❌ También falló el fallback: {str(e2)}")
            return True
        
        # 14. Verificación final del archivo
        try:
            # Cargar el archivo final para verificar que es reproducible
            final_sound = AudioSegment.from_file(audio_path)
            final_duration = final_sound.duration_seconds
            final_level = final_sound.dBFS
            
            logger.info(f"✅ VERIFICACIÓN FINAL: duración={final_duration:.2f}s, nivel={final_level:.2f}dB")
            
            if final_duration < 0.3:
                logger.error(f"❌ Duración final muy corta: {final_duration:.2f}s")
                if os.path.exists(preprocessed_path):
                    logger.info("🔄 Restaurando audio preprocesado como último recurso")
                    backup_sound = AudioSegment.from_file(preprocessed_path)
                    backup_sound.export(audio_path, format="wav")
        except Exception as e:
            logger.error(f"❌ Error en verificación final: {str(e)}")
        
        logger.info(f"✅ PREPROCESAMIENTO COMPLETO: {audio_path}")
        
        # 15. Verificar el archivo final
        if os.path.exists(audio_path):
            final_size = os.path.getsize(audio_path)
            logger.info(f"📊 Tamaño final: {final_size/1024:.2f} KB")
            
            if final_size == 0:
                logger.error("❌ El archivo final está vacío, restaurando original")
                if os.path.exists(orig_path):
                    import shutil
                    shutil.copy(orig_path, audio_path)
        else:
            logger.error("❌ El archivo final no existe, procesamiento fallido")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error general al preprocesar audio: {str(e)}")
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
        logger.info("🔥 Iniciando warmup del modelo de voz...")
        
        encoder = get_voice_encoder()
        if encoder is None:
            logger.error("❌ No se pudo obtener el codificador de voz")
            return {
                "status": "error",
                "message": "No se pudo cargar el modelo de voz",
                "model_loaded": False
            }
        
        # Verificar que el modelo esté realmente cargado con una operación pequeña
        logger.info("🔄 Realizando operación de prueba en el modelo...")
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
        logger.info(f"✅ Warmup completado exitosamente en {process_time:.2f}s")
        
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