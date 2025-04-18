import boto3
import os
import sys
from pathlib import Path

# 📁 Directorio de donde importamos las claves AWS
keys_dir = Path("/home/alessandro_hp/Documentos/Cursor/DAW_PROYECTO/daw_backend").resolve()
sys.path.insert(0, str(keys_dir))
from keys import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

# 🎙️ Texto del mensaje de captura facial
face_capture_message = (
    "Ahora activaré la cámara para capturar tu rostro. "
    "Por favor, colócate frente a la cámara, mantén el rostro estable y con buena iluminación. "
    "La foto se tomará automáticamente cuando se detecte estabilidad."
)

# 📂 Directorio de salida
audio_dir = "/home/alessandro_hp/Documentos/Cursor/DAW_PROYECTO/daw_frontend/public/audio"
os.makedirs(audio_dir, exist_ok=True)
print(f"✅ Directorio de audio creado o verificado: {audio_dir}")

# Inicializar cliente Polly
try:
    polly_client = boto3.client(
        'polly',
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )
    print("✅ Cliente de AWS Polly inicializado correctamente.")
except Exception as e:
    print(f"❌ Error al inicializar AWS Polly: {e}")
    sys.exit(1)

# 🔊 Ruta de archivo de salida
filename = "faceCapture.mp3"
output_path = os.path.join(audio_dir, filename)

try:
    print("🎤 Generando audio para captura facial...")
    
    response = polly_client.synthesize_speech(
        Text=face_capture_message,
        OutputFormat='mp3',
        VoiceId='Mia',
        Engine='neural'
    )
    
    if "AudioStream" in response:
        with open(output_path, 'wb') as f:
            f.write(response["AudioStream"].read())
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"✅ Audio generado correctamente: {output_path}")
        else:
            print(f"❌ El archivo {output_path} no se generó correctamente.")
    else:
        print("❌ No se recibió AudioStream en la respuesta de Polly.")
except Exception as e:
    print(f"❌ Error durante la generación del audio: {e}")
