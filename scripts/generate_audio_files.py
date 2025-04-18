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

# 4. Usar las variables/funciones

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

# Definir mensajes predefinidos
audio_messages = {
    "welcome": "Bienvenido.",
    "askRegistration": "¿Registrado?",
    "registered": "Iniciar sesión",
    "notRegistered": "Cuenta nueva",
    "listening": "Escuchando",
    "notUnderstood": "Intenta de nuevo",
    "goodbye": "Adiós",
    "askLoginOrRegister": "¿Iniciar o registrar?",
    "login": "Iniciando sesión",
    "register": "Registrándote",
    "voiceLogin": "Di algo",
    "faceLogin": "Mira a la cámara",
    "loginSuccess": "Sesión iniciada",
    "loginError": "Error de identidad",
    
    # Nuevos mensajes para la contraseña braille
    "braillePasswordIntro": "Creando contraseña braille",
    "braillePasswordStart": "Di puntos braille",
    "braillePasswordInstructions": "Siguiente para confirmar, borrar para eliminar",
    "brailleCharacterConfirmed": "Carácter confirmado",
    "brailleCharacterDeleted": "Carácter borrado",
    "braillePasswordSaved": "Contraseña guardada",
    "braillePointsRecognized": "Puntos reconocidos",
    "brailleHelp": "Ayuda braille",
    "brailleError": "Error braille",
    "brailleWaitingNext": "Siguiente carácter",
    
    # Nuevos mensajes para el registro guiado por voz
    "registerVoiceGuide": "Registro guiado",
    "askUserName": "Nombre de usuario",
    "userNameConfirmed": "Usuario confirmado",
    "askEmail": "Correo electrónico",
    "emailConfirmed": "Correo confirmado",
    "passwordPrompt": "Ahora crea tu contraseña",
    "registrationComplete": "Registro completo",
    
    # Nuevos mensajes para grabación de voz biométrica
    "voiceRecordingPrompt": "Graba tu voz",
    "voiceRecordingSample": "Di yo soy y tu nombre",
    "voiceRecordingComplete": "Voz grabada correctamente"
}

# Crear directorio para los archivos de audio si no existe
audio_dir = "daw_frontend/public/audio"
os.makedirs(audio_dir, exist_ok=True)
print(f"✅ Directorio de audio creado o verificado: {audio_dir}")

# Guardar información de los archivos de audio
audio_info = []

# Generar archivos de audio
print("🔊 Generando archivos de audio...")
success_count = 0
total_count = len(audio_messages)

for key, text in audio_messages.items():
    try:
        output_file = f"{audio_dir}/{key}.mp3"
        
        # Generar audio con Amazon Polly
        response = polly_client.synthesize_speech(
            Text=text,
            OutputFormat='mp3',
            VoiceId='Mia', #Voz en español
            Engine='neural'
        )
        
        # Guardar el audio generado
        if "AudioStream" in response:
            with open(output_file, 'wb') as file:
                file.write(response["AudioStream"].read())
            
            # Verificar que el archivo se haya creado correctamente
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                print(f"✅ Archivo de audio generado: {output_file}")
                audio_info.append(key)
                success_count += 1
            else:
                print(f"❌ Error: El archivo {output_file} no se creó correctamente.")
        else:
            print(f"❌ Error: No se recibió AudioStream para el mensaje '{key}'.")
    except Exception as e:
        print(f"❌ Error al generar audio para '{key}': {e}")

# Guardar información de los archivos de audio en un JSON
audio_info_file = f"{audio_dir}/audio_info.json"
with open(audio_info_file, 'w') as f:
    json.dump(audio_info, f)
print(f"✅ Información de audio guardada en: {audio_info_file}")

# Mostrar resumen
print(f"\n🎉 Generación de audio completada: {success_count}/{total_count} archivos generados exitosamente.")
if success_count < total_count:
    print(f"⚠️  {total_count - success_count} archivos no pudieron ser generados.")
else:
    print("✅ Todos los archivos de audio se generaron correctamente.")