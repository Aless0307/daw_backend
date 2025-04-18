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
try:
    from keys import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
except ImportError:
    print("❌ No se pudieron importar las claves AWS. Usando valores predeterminados para pruebas.")
    AWS_REGION = 'us-east-1'
    AWS_ACCESS_KEY_ID = 'test-key'
    AWS_SECRET_ACCESS_KEY = 'test-secret'

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

# Definir mensajes para la edición de contraseña
password_edit_messages = {
    "edit_password_question": "¿Editar contraseña?",
    "edit_position_prompt": "¿Qué posición?",
    "edit_points_prompt": "¿Qué puntos?",
    "edit_confirm": "¿Confirmar cambios?",
    "edit_success": "Cambios guardados",
    "edit_cancelled": "Edición cancelada",
    "position_selected": "Posición seleccionada",
    "edit_from_scratch": "¿Empezar de cero?"
}

print("🔊 Generando archivos de audio para edición de contraseña...")
success_count = 0
total_count = len(password_edit_messages)

for key, text in password_edit_messages.items():
    try:
        output_file = f"{audio_dir}/{key}.mp3"
        
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
            
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                print(f"✅ Archivo de audio generado: {output_file}")
                success_count += 1
            else:
                print(f"❌ Error: El archivo {output_file} no se creó correctamente.")
        else:
            print(f"❌ Error: No se recibió AudioStream para '{key}'.")
    except Exception as e:
        print(f"❌ Error al generar audio para '{key}': {e}")

# Mostrar resumen
print(f"\n🎉 Generación de audio completada: {success_count}/{total_count} archivos generados exitosamente.")
if success_count < total_count:
    print(f"⚠️  {total_count - success_count} archivos no pudieron ser generados.")
else:
    print("✅ Todos los archivos de audio se generaron correctamente.")