import boto3
import os
import json
import sys
from pathlib import Path

# 1. Obtener la ruta del directorio que contiene keys.py
keys_dir = Path("/home/alessandro_hp/Documentos/Cursor/DAW_PROYECTO/daw_backend").resolve()

# 2. Agregar al path de Python
sys.path.insert(0, str(keys_dir))

# 3. Importar normalmente
from keys import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

# Verificar credenciales
if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
    print("⚠️  Advertencia: No se encontraron credenciales de AWS en las variables de entorno.")
    print("Se utilizarán credenciales de ejemplo para este script.")
    
    # Para propósitos de desarrollo solamente - NO usar en producción
    aws_access_key_id = AWS_ACCESS_KEY_ID
    aws_secret_access_key = AWS_SECRET_ACCESS_KEY

# Inicializar cliente de Polly
try:
    polly_client = boto3.client(
        'polly',
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )
    print("✅ Cliente de AWS Polly inicializado correctamente.")
except Exception as e:
    print(f"❌ Error al inicializar cliente AWS Polly: {e}")
    sys.exit(1)

# Crear directorio para los archivos de audio si no existe
audio_dir = "/home/alessandro_hp/Documentos/Cursor/DAW_PROYECTO/daw_frontend/public/audio"
os.makedirs(audio_dir, exist_ok=True)
print(f"✅ Directorio de audio creado o verificado: {audio_dir}")

# Generar archivos de audio para números del 1 al 20
print("🔢 Generando archivos de audio para números del 1 al 20...")
success_count = 0
total_count = 20

# Guardar información de los archivos de audio
number_audio_info = []

# Definir mensajes para cada posición (del 1 al 20)
position_messages = {
    f"position_{i}": f"Posición {i}" for i in range(1, 21)
}

# Generar texto para cada número
for number in range(1, 21):
    try:
        # Definir el nombre de archivo
        filename = f"position_{number}.mp3"
        output_file = f"{audio_dir}/{filename}"
        
        # Texto a convertir a voz
        text = position_messages[f"position_{number}"]
        
        # Generar audio con Amazon Polly
        response = polly_client.synthesize_speech(
            Text=text,
            OutputFormat='mp3',
            VoiceId='Mia',  # Voz en español
            Engine='neural'
        )
        
        # Guardar el audio generado
        if "AudioStream" in response:
            with open(output_file, 'wb') as file:
                file.write(response["AudioStream"].read())
            
            # Verificar que el archivo se haya creado correctamente
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                print(f"✅ Archivo de audio generado: {output_file}")
                number_audio_info.append(f"position_{number}")
                success_count += 1
            else:
                print(f"❌ Error: El archivo {output_file} no se creó correctamente.")
        else:
            print(f"❌ Error: No se recibió AudioStream para el número {number}.")
    except Exception as e:
        print(f"❌ Error al generar audio para número {number}: {e}")

# Guardar información de los archivos de audio en un JSON
number_audio_info_file = f"{audio_dir}/number_audio_info.json"
with open(number_audio_info_file, 'w') as f:
    json.dump(number_audio_info, f)
print(f"✅ Información de audio de números guardada en: {number_audio_info_file}")

# Mostrar resumen
print(f"\n🎉 Generación de audio completada: {success_count}/{total_count} archivos de números generados exitosamente.")
if success_count < total_count:
    print(f"⚠️  {total_count - success_count} archivos no pudieron ser generados.")
else:
    print("✅ Todos los archivos de audio de números se generaron correctamente.")