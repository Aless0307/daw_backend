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

# Variables globales para los clientes
blob_service_client = None
container_client = None
is_azure_available = False

def init_azure_storage():
    """
    Inicializa la conexión con Azure Storage.
    Returns:
        bool: True si la conexión fue exitosa, False en caso contrario
    """
    global blob_service_client, container_client, is_azure_available
    
    try:
        # Crear cliente de Azure Storage
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
        
        # Verificar conexión
        container_client.get_container_properties()
        
        is_azure_available = True
        logger.info("Conexión a Azure Storage establecida correctamente")
        return True
        
    except Exception as e:
        is_azure_available = False
        if IS_PRODUCTION:
            logger.error(f"Error al conectar con Azure Storage: {str(e)}")
        else:
            logger.warning("Azure Storage no disponible en desarrollo")
        return False

# Intentar inicializar Azure Storage al importar el módulo
init_azure_storage()

async def upload_voice_recording(file_path: str, user_email: str) -> str:
    """
    Sube un archivo de audio a Azure Storage y devuelve la URL de vista previa.
    
    Args:
        file_path: Ruta al archivo de audio
        user_email: Email del usuario para nombrar el archivo
        
    Returns:
        str: URL de vista previa del archivo con token SAS o None si falla
    """
    if not is_azure_available:
        logger.warning("Azure Storage no disponible, no se puede subir el archivo")
        return None
        
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
        return None

async def download_voice_recording(file_name: str) -> str:
    """
    Descarga un archivo de audio de Azure Storage.
    
    Args:
        file_name: Nombre del archivo a descargar
        
    Returns:
        str: Ruta local del archivo descargado o None si falla
    """
    if not is_azure_available:
        logger.warning("Azure Storage no disponible, no se puede descargar el archivo")
        return None
        
    try:
        # Crear cliente para el blob usando el nombre del blob decodificado
        blob_client = container_client.get_blob_client(file_name)
        
        # Verificar si el blob existe
        if not blob_client.exists():
            logger.error(f"El blob {file_name} no existe en el contenedor {AZURE_CONTAINER_NAME}")
            raise Exception(f"El archivo de voz {file_name} no existe en el almacenamiento")
        
        # Descargar archivo
        local_path = f"/tmp/{file_name}"
        with open(local_path, "wb") as download_file:
            download_file.write(blob_client.download_blob().readall())
            
        logger.info(f"Archivo descargado exitosamente a: {local_path}")
        
        return local_path
        
    except Exception as e:
        logger.error(f"Error al descargar archivo de Azure Storage: {str(e)}")
        return None

def get_azure_status():
    """
    Devuelve el estado actual de la conexión con Azure Storage.
    """
    return {
        "available": is_azure_available,
        "container": AZURE_CONTAINER_NAME if is_azure_available else None,
        "last_check": datetime.now().isoformat()
    } 