from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, ContentSettings
from datetime import datetime, timedelta
import os
import uuid
import logging
from config import (
    AZURE_STORAGE_CONNECTION_STRING, 
    AZURE_CONTAINER_NAME,
    ENVIRONMENT,
    IS_PRODUCTION
)
from urllib.parse import unquote

# Configurar logging
logging.basicConfig(
    level=logging.INFO if IS_PRODUCTION else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('azure_storage.log')
    ]
)
logger = logging.getLogger(__name__)

# Log del entorno actual
logger.info(f"Ejecutando en entorno: {ENVIRONMENT}")

# Crear cliente de Azure Storage
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)

# Crear contenedor si no existe
try:
    if not container_client.exists():
        logger.info(f"Creando contenedor {AZURE_CONTAINER_NAME}")
        container_client.create_container()
        logger.info(f"Contenedor {AZURE_CONTAINER_NAME} creado exitosamente")
    else:
        logger.info(f"Contenedor {AZURE_CONTAINER_NAME} ya existe")
except Exception as e:
    logger.error(f"Error al verificar/crear contenedor: {str(e)}")
    raise

async def upload_voice_recording(file_path: str, user_email: str) -> str:
    """
    Sube un archivo de audio a Azure Storage y devuelve la URL de vista previa.
    
    Args:
        file_path: Ruta al archivo de audio
        user_email: Email del usuario para nombrar el archivo
        
    Returns:
        str: URL de vista previa del archivo con token SAS
    """
    try:
        # Generar nombre único para el archivo
        file_name = f"voices/{user_email}_{os.path.basename(file_path)}"
        logger.info(f"Subiendo archivo: {file_name}")
        
        # Crear cliente para el blob
        blob_client = container_client.get_blob_client(file_name)
        
        # Configurar Content-Type para audio/wav
        content_settings = ContentSettings(content_type="audio/wav")
        
        # Subir archivo
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, content_settings=content_settings, overwrite=True)
        
        # Generar token SAS para lectura (válido por 1 año)
        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=AZURE_CONTAINER_NAME,
            blob_name=file_name,
            account_key=blob_service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(days=365)
        )
        
        # Construir URL de vista previa
        preview_url = f"{blob_client.url}?{sas_token}"
        logger.info(f"Archivo subido exitosamente. URL: {preview_url}")
        
        return preview_url
        
    except Exception as e:
        logger.error(f"Error al subir archivo a Azure Storage: {str(e)}")
        raise

async def download_voice_recording(blob_url: str, local_path: str) -> None:
    """
    Descarga un archivo de audio de Azure Storage.
    
    Args:
        blob_url: URL del blob en Azure Storage
        local_path: Ruta local donde guardar el archivo
    """
    try:
        # Extraer el nombre del blob de la URL y decodificarlo
        # La URL tiene formato: https://<account>.blob.core.windows.net/<container>/<blob_name>?<sas_token>
        # Necesitamos extraer solo el <blob_name> y decodificarlo
        blob_name = unquote(blob_url.split(f"{AZURE_CONTAINER_NAME}/")[1].split("?")[0])
        logger.info(f"Descargando archivo (nombre decodificado): {blob_name}")
        
        # Crear cliente para el blob usando el nombre del blob decodificado
        blob_client = container_client.get_blob_client(blob_name)
        
        # Verificar si el blob existe
        if not blob_client.exists():
            logger.error(f"El blob {blob_name} no existe en el contenedor {AZURE_CONTAINER_NAME}")
            raise Exception(f"El archivo de voz {blob_name} no existe en el almacenamiento")
        
        # Descargar archivo
        with open(local_path, "wb") as download_file:
            download_file.write(blob_client.download_blob().readall())
            
        logger.info(f"Archivo descargado exitosamente a: {local_path}")
        
    except Exception as e:
        logger.error(f"Error al descargar archivo de Azure Storage: {str(e)}")
        raise 