from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, ContentSettings
from datetime import datetime, timedelta
import os
import uuid
import logging
from config import AZURE_STORAGE_CONNECTION_STRING, AZURE_STORAGE_CONTAINER_NAME

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_blob_service_client():
    """Crea y retorna un cliente de Azure Blob Storage"""
    try:
        logger.info("Conectando a Azure Blob Storage")
        return BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    except Exception as e:
        logger.error(f"Error al conectar con Azure Blob Storage: {str(e)}")
        raise

def upload_voice_recording(audio_file, user_id=None):
    """
    Sube un archivo de audio a Azure Blob Storage y genera una URL firmada
    
    Args:
        audio_file: El archivo de audio a subir
        user_id: ID del usuario al que pertenece la grabación (opcional)
    
    Returns:
        str: URL firmada del archivo subido
    """
    try:
        # Crear un nombre único para el blob usando UUID
        unique_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        user_prefix = f"{user_id}_" if user_id else ""
        blob_name = f"voice_recordings/{user_prefix}{timestamp}_{unique_id}.wav"
        
        logger.info(f"Iniciando subida de archivo a Azure Storage: {blob_name}")
        
        # Obtener el cliente del servicio
        blob_service_client = get_blob_service_client()
        
        # Obtener las credenciales de la cadena de conexión
        account_name = blob_service_client.account_name
        account_key = blob_service_client.credential.account_key
        
        # Configurar el content type para reproducción en el navegador
        content_settings = ContentSettings(
            content_type='audio/wav',
            content_disposition='inline'  # Esto hace que se reproduzca en lugar de descargarse
        )
        
        # Subir el archivo
        container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)
        blob_client = container_client.get_blob_client(blob_name)
        
        # Verificar si existe el contenedor, si no, crearlo
        try:
            container_props = container_client.get_container_properties()
        except Exception:
            logger.info(f"Contenedor {AZURE_STORAGE_CONTAINER_NAME} no existe, creándolo...")
            container_client = blob_service_client.create_container(AZURE_STORAGE_CONTAINER_NAME)
        
        # Subir el archivo
        blob_client.upload_blob(
            audio_file,
            overwrite=True,
            content_settings=content_settings
        )
        
        logger.info(f"Archivo subido exitosamente a Azure Storage: {blob_name}")
        
        # Generar URL firmada con expiración de 1 año
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=AZURE_STORAGE_CONTAINER_NAME,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(days=365),
            start=datetime.utcnow() - timedelta(minutes=5)
        )
        
        # Construir la URL completa con el token SAS
        base_url = f"https://{account_name}.blob.core.windows.net/{AZURE_STORAGE_CONTAINER_NAME}/{blob_name}"
        blob_url = f"{base_url}?{sas_token}"
        
        logger.info(f"URL de Azure generada: {base_url}")
        
        return blob_url
    except Exception as e:
        logger.error(f"Error al subir el archivo a Azure Storage: {str(e)}")
        raise 