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
audio_dir = "daw_frontend/public/audio/braille"
os.makedirs(audio_dir, exist_ok=True)
print(f"✅ Directorio de audio para braille creado o verificado: {audio_dir}")

# Definir el mapeo braille
braille_map = {
    '1': 'a', '12': 'b', '14': 'c', '145': 'd', '15': 'e',
    '124': 'f', '1245': 'g', '125': 'h', '24': 'i', '245': 'j',
    '13': 'k', '123': 'l', '134': 'm', '1345': 'n', '135': 'o',
    '1234': 'p', '12345': 'q', '1235': 'r', '234': 's', '2345': 't',
    '136': 'u', '1236': 'v', '2456': 'w', '1346': 'x', '13456': 'y', '1356': 'z',
    '3456': '#', 'numero_16': '1', 'numero_126': '2', 'numero_146': '3', 'numero_1456': '4', 'numero_156': '5',
    'numero_1246': '6', 'numero_12456': '7', 'numero_1256': '8', 'numero_246': '9', 'numero_2456': '0'
}

# Función para describir los puntos
def get_dots_description(dots_str):
    if not dots_str or dots_str.startswith('numero_'):
        # Si es un número, extraer solo los dígitos después del prefijo
        if dots_str.startswith('numero_'):
            dots_str = dots_str[7:]
        else:
            return ''
    
    dots = [int(d) for d in dots_str]
    
    if len(dots) == 1:
        return f"punto {dots[0]}"
    elif len(dots) == 2:
        return f"puntos {dots[0]} y {dots[1]}"
    else:
        last_dot = dots[-1]
        initial_dots = ', '.join(str(d) for d in dots[:-1])
        return f"puntos {initial_dots} y {last_dot}"

# Crear archivos de audio para cada carácter braille
print("🔊 Generando archivos de audio para caracteres braille...")
success_count = 0
total_count = len(braille_map)

for dots, char in braille_map.items():
    try:
        dots_description = get_dots_description(dots)
        
        # Nombre base del archivo
        file_base = f"braille_{char}"
        
        # Archivo para indicar combinación completa
        output_file_info = f"{audio_dir}/{file_base}_info.mp3"
        
        # Texto para describir la combinación (solo puntos, sin mencionar el carácter)
        text_info = f"Has seleccionado {dots_description}."
        
        # Generar audio con Amazon Polly para la descripción de puntos (sin mencionar el carácter)
        response = polly_client.synthesize_speech(
            Text=text_info,
            OutputFormat='mp3',
            VoiceId='Mia',  # Voz en español
            Engine='neural'
        )
        
        # Guardar el audio generado
        if "AudioStream" in response:
            with open(output_file_info, 'wb') as file:
                file.write(response["AudioStream"].read())
            
            if os.path.exists(output_file_info) and os.path.getsize(output_file_info) > 0:
                print(f"✅ Archivo de audio generado: {output_file_info}")
                success_count += 1
            else:
                print(f"❌ Error: El archivo {output_file_info} no se creó correctamente.")
        else:
            print(f"❌ Error: No se recibió AudioStream para '{file_base}_info'.")
            
        # Archivo para confirmar puntos (sin mencionar el carácter)
        output_file_char = f"{audio_dir}/{file_base}.mp3"
        
        # Texto para confirmar puntos (sin mencionar el carácter)
        text_char = "Puntos confirmados."
        
        # Generar audio con Amazon Polly para la simple mención
        response = polly_client.synthesize_speech(
            Text=text_char,
            OutputFormat='mp3',
            VoiceId='Mia',  # Voz en español
            Engine='neural'
        )
        
        # Guardar el audio generado
        if "AudioStream" in response:
            with open(output_file_char, 'wb') as file:
                file.write(response["AudioStream"].read())
            
            if os.path.exists(output_file_char) and os.path.getsize(output_file_char) > 0:
                print(f"✅ Archivo de audio generado: {output_file_char}")
                success_count += 1
            else:
                print(f"❌ Error: El archivo {output_file_char} no se creó correctamente.")
        else:
            print(f"❌ Error: No se recibió AudioStream para '{file_base}'.")
            
    except Exception as e:
        print(f"❌ Error al generar audio para '{dots}' ({char}): {e}")

# Crear audios adicionales para el resumen de contraseña
summary_texts = {
    "password_intro": "Tu contraseña ha sido creada. A continuación escucharás la secuencia de puntos seleccionados.",
    "password_completed": "Tu contraseña ha sido guardada correctamente.",
    "password_char_prefix": "Posición"
}

for key, text in summary_texts.items():
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
total_count = len(braille_map) * 2 + len(summary_texts)  # Cada carácter tiene 2 archivos + audios de resumen
print(f"\n🎉 Generación de audio completada: {success_count}/{total_count} archivos generados exitosamente.")
if success_count < total_count:
    print(f"⚠️  {total_count - success_count} archivos no pudieron ser generados.")
else:
    print("✅ Todos los archivos de audio se generaron correctamente.") 