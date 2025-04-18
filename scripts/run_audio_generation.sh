#!/bin/bash

# Colores para los mensajes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Iniciando generación de archivos de audio...${NC}"

# Instalar dependencias si es necesario
echo -e "${YELLOW}Instalando dependencias...${NC}"
pip install boto3

# Ejecutar el script de generación de audio
echo -e "${YELLOW}Generando archivos de audio...${NC}"
python generate_audio_files.py

# Verificar si la generación fue exitosa
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Error al generar los archivos de audio.${NC}"
    exit 1
fi

# Verificar los archivos generados
echo -e "${YELLOW}Verificando archivos de audio...${NC}"
python verify_audio_files.py

# Verificar si la verificación fue exitosa
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Error al verificar los archivos de audio.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Proceso completado. Los archivos de audio han sido generados y verificados correctamente.${NC}"
echo -e "${GREEN}✅ Los archivos están disponibles en la carpeta ../daw_frontend/public/audio${NC}" 