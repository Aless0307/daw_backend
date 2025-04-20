import boto3
import os
import sys
from pathlib import Path

# Configuración de AWS Polly (ajusta según tu entorno)
keys_dir = Path("/home/alessandro_hp/Documentos/Cursor/DAW_PROYECTO/daw_backend").resolve()
sys.path.insert(0, str(keys_dir))

try:
    from keys import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
except ImportError:
    print("❌ No se pudieron importar las claves AWS. Usando valores predeterminados para pruebas.")
    AWS_REGION = 'us-east-1'
    AWS_ACCESS_KEY_ID = 'test-key'
    AWS_SECRET_ACCESS_KEY = 'test-secret'

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

# Directorio de destino para el audio
AUDIO_DIR = "/home/alessandro_hp/Documentos/Cursor/DAW_PROYECTO/daw_frontend/public/audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

# Texto del mensaje de ayuda para el correo electrónico
EMAIL_HELP_TEXT = (
    "Por favor, dicta tu correo electrónico."
)

LOGIN_OPTIONS_TEXT = (
    "Facial, voz, braille."
)

PASSWORD_PROMPT_TEXT = (
    "Por favor, dicta tu contraseña."
)

PASSWORD_INTRO_TEXT = (
    "Introduce tu contraseña."
)

PASSWORD_COMPLETED_TEXT = (
    "Contraseña introducida correctamente."
)

EDIT_PASSWORD_QUESTION_TEXT = (
    "¿Deseas editar tu contraseña?"
)

# Ya no se generan audios de posición por carácter, según preferencia del usuario
# Se recomienda eliminar position_1.mp3, position_2.mp3, position_3.mp3 si existen en el frontend
NEW_AUDIO_FILES = [
    ("emailHelp.mp3", EMAIL_HELP_TEXT),
    ("loginOptions.mp3", LOGIN_OPTIONS_TEXT),
    ("passwordPrompt.mp3", PASSWORD_PROMPT_TEXT),
    ("password_intro.mp3", PASSWORD_INTRO_TEXT),
    ("password_completed.mp3", PASSWORD_COMPLETED_TEXT),
    ("edit_password_question.mp3", EDIT_PASSWORD_QUESTION_TEXT),
    # Positional audios eliminados
]

for filename, text in NEW_AUDIO_FILES:
    audio_path = os.path.join(AUDIO_DIR, filename)
    print(f"🔊 Generando audio: {audio_path}")
    try:
        response = polly_client.synthesize_speech(
            Text=text,
            OutputFormat='mp3',
            VoiceId='Mia',  # Voz en español
            Engine='neural'
        )
        with open(audio_path, 'wb') as f:
            f.write(response['AudioStream'].read())
        print(f"✅ Audio generado correctamente: {audio_path}")
    except Exception as e:
        print(f"❌ Error al generar el audio {filename}: {e}")
