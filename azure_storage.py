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
        # Verificar que el archivo existe
        if not os.path.exists(file_path):
            logger.error(f"El archivo {file_path} no existe")
            return None
            
        # Generar nombre único para el archivo
        file_name = f"voices/{user_email}_{os.path.basename(file_path)}"
        logger.info(f"Subiendo archivo: {file_name}")
        
        # Crear cliente para el blob
        blob_client = container_client.get_blob_client(file_name)
        
        # Configurar tipo de contenido
        content_settings = ContentSettings(content_type="audio/wav")
        
        # Subir archivo
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True, content_settings=content_settings)
        
        logger.info(f"Archivo subido exitosamente: {file_name}")
        
        # Generar SAS token para acceso de 1 año
        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=AZURE_CONTAINER_NAME,
            blob_name=file_name,
            account_key=blob_service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(days=365)
        )
        
        # Construir URL con token SAS
        blob_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{AZURE_CONTAINER_NAME}/{file_name}?{sas_token}"
        
        return blob_url
        
    except Exception as e:
        logger.error(f"Error al subir archivo a Azure Storage: {str(e)}")
        return None

async def download_voice_recording(blob_url: str, local_path: str = None) -> str:
    """
    Descarga un archivo de audio de Azure Storage.
    
    Args:
        blob_url: URL del blob o nombre del archivo en Azure Storage
        local_path: Ruta local donde guardar el archivo (opcional)
        
    Returns:
        str: Ruta local del archivo descargado o None si falla
    """
    if not is_azure_available:
        logger.warning("Azure Storage no disponible, no se puede descargar el archivo")
        return None
        
    try:
        # Extraer el nombre del blob de la URL si es una URL completa
        if blob_url.startswith('http'):
            # La URL tiene formato: https://<account>.blob.core.windows.net/<container>/<blob_name>?<sas_token>
            blob_name = unquote(blob_url.split(f"{AZURE_CONTAINER_NAME}/")[1].split("?")[0])
        else:
            # Si no es una URL, usar el nombre directamente
            blob_name = blob_url
            
        logger.info(f"Descargando archivo (nombre decodificado): {blob_name}")
        
        # Crear cliente para el blob
        blob_client = container_client.get_blob_client(blob_name)
        
        # Verificar si el blob existe
        if not blob_client.exists():
            logger.error(f"El blob {blob_name} no existe en el contenedor {AZURE_CONTAINER_NAME}")
            raise Exception(f"El archivo de voz {blob_name} no existe en el almacenamiento")
        
        # Si no se proporciona local_path o está vacío, crear uno temporal
        if not local_path:
            local_path = f"/tmp/{os.path.basename(blob_name)}"
        
        # Directorio temporal para archivos
        temp_dir = "./temp_files"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        # Asegurarse de que la ruta local es válida
        if not local_path or local_path == "":
            local_path = f"{temp_dir}/{os.path.basename(blob_name)}"
            
        # Asegurarse de que el directorio existe
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        
        logger.info(f"Guardando archivo en: {local_path}")
        
        # Descargar archivo
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