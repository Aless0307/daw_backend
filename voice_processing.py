from resemblyzer import preprocess_wav, VoiceEncoder
import numpy as np
import librosa
import io
import os

def extract_voice_embedding(audio_file):
    """
    Extrae el embedding de voz usando Resemblyzer
    
    Args:
        audio_file: El archivo de audio a procesar
        
    Returns:
        numpy.ndarray: El embedding de voz
    """
    try:
        # Cargar el audio
        audio, sr = librosa.load(audio_file, sr=16000)
        
        # Preprocesar el audio
        processed_audio = preprocess_wav(audio)
        
        # Crear el encoder
        encoder = VoiceEncoder()
        
        # Extraer el embedding
        embedding = encoder.embed_utterance(processed_audio)
        
        return embedding
        
    except Exception as e:
        print(f"Error al procesar el audio: {str(e)}")
        raise

def compare_voice_embeddings(embedding1, embedding2, threshold=0.7):
    """
    Compara dos embeddings de voz
    
    Args:
        embedding1: Primer embedding
        embedding2: Segundo embedding
        threshold: Umbral de similitud (0-1)
        
    Returns:
        bool: True si los embeddings son similares
    """
    try:
        # Calcular la similitud del coseno
        similarity = np.dot(embedding1, embedding2) / (np.linalg.norm(embedding1) * np.linalg.norm(embedding2))
        
        return similarity >= threshold
        
    except Exception as e:
        print(f"Error al comparar embeddings: {str(e)}")
        raise 