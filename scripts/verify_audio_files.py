import os
import json
import sys

# Definir la ruta de los archivos de audio
audio_dir = "/home/alessandro_hp/Documentos/Cursor/DAW_PROYECTO/daw_frontend/public/audio"

# Comprobar que el directorio existe
if not os.path.exists(audio_dir):
    print(f"❌ Error: El directorio {audio_dir} no existe.")
    sys.exit(1)

print(f"✅ Verificando archivos de audio numéricos en: {audio_dir}")

# Verificar archivos de audio numéricos
missing_files = []
total_count = 20
found_count = 0

for number in range(1, 21):
    filename = f"position_{number}.mp3"
    file_path = os.path.join(audio_dir, filename)
    
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        found_count += 1
        print(f"✅ Archivo encontrado: {filename}")
    else:
        missing_files.append(filename)
        print(f"❌ Archivo faltante: {filename}")

# Verificar archivo JSON de información
json_file = os.path.join(audio_dir, "number_audio_info.json")
if os.path.exists(json_file) and os.path.getsize(json_file) > 0:
    try:
        with open(json_file, 'r') as f:
            info = json.load(f)
        print(f"✅ Archivo JSON encontrado con {len(info)} entradas")
    except Exception as e:
        print(f"❌ Error al leer el archivo JSON: {e}")
else:
    print(f"❌ Archivo JSON faltante: {json_file}")

# Mostrar resumen
print(f"\n📊 Resumen de verificación:")
print(f"   - Archivos encontrados: {found_count}/{total_count}")
if missing_files:
    print(f"   - Archivos faltantes: {len(missing_files)}")
    for file in missing_files:
        print(f"     - {file}")
else:
    print("   - Todos los archivos están presentes")

# Sugerir acciones si faltan archivos
if missing_files:
    print("\n🔄 Sugerencia: Ejecute el script generate_number_audio.sh para generar los archivos faltantes")