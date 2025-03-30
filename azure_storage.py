from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, ContentSettings
from datetime import datetime, timedelta
import os
import uuid
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) # para agregar la carpeta padre al path y poder importar las keys
from keys import CONNECTION_STRING, NOMBRE_CONTENEDOR

# Configuración de Azure Storage
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

def get_blob_service_client():
    """Crea y retorna un cliente de Azure Blob Storage"""
    return BlobServiceClient.from_connection_string(CONNECTION_STRING)

def upload_voice_recording(audio_file, user_id):
    """
    Sube un archivo de audio a Azure Blob Storage y genera una URL firmada
    
    Args:
        audio_file: El archivo de audio a subir
        user_id: ID del usuario al que pertenece la grabación (no usado actualmente)
    
    Returns:
        str: URL firmada del archivo subido
    """
    try:
        # Crear un nombre único para el blob usando UUID
        unique_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        blob_name = f"voice_recordings/{timestamp}_{unique_id}.wav"
        
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
        container_client = blob_service_client.get_container_client(NOMBRE_CONTENEDOR)
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(
            audio_file,
            overwrite=True,
            content_settings=content_settings
        )
        
        # Generar URL firmada con expiración de 1 año
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=NOMBRE_CONTENEDOR,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(days=365),
            start=datetime.utcnow() - timedelta(minutes=5)
        )
        
        # Construir la URL completa con el token SAS
        # Usar https:// explícitamente
        base_url = f"https://{account_name}.blob.core.windows.net/{NOMBRE_CONTENEDOR}/{blob_name}"
        blob_url = f"{base_url}?{sas_token}"
        
        return blob_url
    except Exception as e:
        print(f"Error al subir el archivo a Azure Storage: {str(e)}")
        raise 