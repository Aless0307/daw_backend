#!/bin/bash

# Script para ejecutar la generación de archivos de audio numéricos

echo "🚀 Iniciando generación de archivos de audio numéricos..."

# Navegar al directorio correcto
cd "$(dirname "$0")"

# Ejecutar el script de Python
python3 generate_number_audio_files.py

echo "✅ Proceso de generación de audio numérico completado"