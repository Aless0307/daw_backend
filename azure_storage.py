from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, ContentSettings
from azure.core.exceptions import ResourceNotFoundError, AzureError
from datetime import datetime, timedelta
import os
import uuid
import logging
import traceback
import requests
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

# Verificar inicialmente el acceso a Azure
try:
    logger.info("🔍 Verificando variables de entorno para Azure Storage...")
    if not AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_CONNECTION_STRING.strip() == "":
        logger.warning("⚠️ AZURE_STORAGE_CONNECTION_STRING no configurada o vacía")
        is_azure_available = False
    elif not AZURE_CONTAINER_NAME or AZURE_CONTAINER_NAME.strip() == "":
        logger.warning("⚠️ AZURE_CONTAINER_NAME no configurado o vacío")
        is_azure_available = False
    else:
        logger.info("✅ Variables de entorno para Azure Storage configuradas correctamente")
except Exception as e:
    logger.error(f"❌ Error al verificar variables de Azure: {str(e)}")
    is_azure_available = False

def init_azure_storage():
    """
    Inicializa la conexión con Azure Storage.
    Returns:
        bool: True si la conexión fue exitosa, False en caso contrario
    """
    global blob_service_client, container_client, is_azure_available
    
    logger.info("🔄 Inicializando conexión a Azure Storage...")
    
    # Verificar que la cadena de conexión no está vacía
    if not AZURE_STORAGE_CONNECTION_STRING:
        logger.error("❌ AZURE_STORAGE_CONNECTION_STRING está vacía")
        return False
        
    if not AZURE_CONTAINER_NAME:
        logger.error("❌ AZURE_CONTAINER_NAME está vacío")
        return False
        
    logger.info(f"📦 Intentando conectar a Azure Storage - Contenedor: {AZURE_CONTAINER_NAME}")
    logger.info(f"🔑 Primeros 10 caracteres de la conexión: {AZURE_STORAGE_CONNECTION_STRING[:10]}...")
    
    try:
        # Crear cliente de Azure Storage
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        logger.info(f"✅ Cliente de servicio creado - Cuenta: {blob_service_client.account_name}")
        
        # Verificar endpoint
        logger.info(f"🌐 URL del servicio: {blob_service_client.url}")
        
        # Probar conectividad básica
        account_info = blob_service_client.get_account_information()
        logger.info(f"✅ Conexión exitosa - SKU: {account_info['sku_name']}, API: {account_info['account_kind']}")
        
        # Verificar que el contenedor existe
        container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
        logger.info("🔍 Verificando existencia del contenedor...")
        
        if container_client.exists():
            logger.info(f"✅ Contenedor {AZURE_CONTAINER_NAME} encontrado")
            
            # Verificar permisos del contenedor
            try:
                props = container_client.get_container_properties()
                public_access = props.get('public_access', 'ninguno')
                logger.info(f"🔒 Nivel de acceso público del contenedor: {public_access}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudieron obtener propiedades del contenedor: {str(e)}")
        else:
            # Intentar crear el contenedor
            logger.warning(f"⚠️ Contenedor {AZURE_CONTAINER_NAME} no existe, intentando crear...")
            try:
                container_client.create_container()
                logger.info(f"✅ Contenedor {AZURE_CONTAINER_NAME} creado exitosamente")
            except Exception as e:
                logger.error(f"❌ Error al crear contenedor: {str(e)}")
                return False
        
        # Probar CORS haciendo una solicitud OPTIONS
        try:
            test_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{AZURE_CONTAINER_NAME}"
            logger.info(f"🌐 Probando CORS con OPTIONS a: {test_url}")
            
            headers = {
                'Origin': 'https://dawbackend-production.up.railway.app',
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'Authorization,Content-Type'
            }
            
            response = requests.options(test_url, headers=headers, timeout=5)
            logger.info(f"📝 Respuesta CORS - Código: {response.status_code}")
            
            if 'Access-Control-Allow-Origin' in response.headers:
                logger.info(f"✅ CORS permitido para origen: {response.headers['Access-Control-Allow-Origin']}")
            else:
                logger.warning("⚠️ La respuesta no incluye encabezados CORS")
                for header, value in response.headers.items():
                    logger.info(f"📝 {header}: {value}")
        except Exception as e:
            logger.warning(f"⚠️ Error al probar CORS: {str(e)}")
            
        # Si llegamos aquí, la conexión fue exitosa
        is_azure_available = True
        logger.info("✅ Conexión a Azure Storage establecida correctamente")
        return True
        
    except ResourceNotFoundError as e:
        is_azure_available = False
        logger.error(f"❌ Recurso no encontrado en Azure Storage: {str(e)}")
        return False
    except AzureError as e:
        is_azure_available = False
        logger.error(f"❌ Error de Azure: {str(e)}")
        return False
    except Exception as e:
        is_azure_available = False
        logger.error(f"❌ Error al conectar con Azure Storage: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
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
    global is_azure_available
    
    # Comprobar disponibilidad de Azure y reintentar si es necesario
    if not await ensure_azure_storage():
        logger.error("❌ Azure Storage no está disponible, imposible subir archivo")
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
    global is_azure_available
    
    # Comprobar disponibilidad de Azure y reintentar si es necesario
    if not await ensure_azure_storage():
        logger.error("❌ Azure Storage no está disponible, imposible descargar archivo")
        return None
    
    try:
        # Validar parámetros
        if not blob_url:
            logger.error("❌ URL del blob es vacía o None")
            return None
            
        logger.info(f"🔍 Intentando descargar archivo: {blob_url}")
        
        # Extraer el nombre del blob de la URL si es una URL completa
        if blob_url.startswith('http'):
            # La URL tiene formato: https://<account>.blob.core.windows.net/<container>/<blob_name>?<sas_token>
            logger.info(f"🔍 Analizando URL del blob: {blob_url}")
            
            try:
                # Extraer el nombre del blob de la URL
                if f"{AZURE_CONTAINER_NAME}/" in blob_url:
                    parts = blob_url.split(f"{AZURE_CONTAINER_NAME}/")
                    if len(parts) > 1:
                        blob_name_with_query = parts[1]
                        # Separar nombre de blob del token SAS
                        blob_name = blob_name_with_query.split("?")[0]
                        blob_name = unquote(blob_name)
                        logger.info(f"✅ Nombre del blob extraído: {blob_name}")
                    else:
                        logger.error(f"❌ No se pudo extraer el nombre del blob de la URL: {blob_url}")
                        return None
                else:
                    logger.error(f"❌ URL no contiene el nombre del contenedor {AZURE_CONTAINER_NAME}")
                    return None
            except Exception as e:
                logger.error(f"❌ Error al analizar URL del blob: {str(e)}")
                return None
        else:
            # Si no es una URL, usar el nombre directamente
            blob_name = blob_url
            logger.info(f"✅ Usando nombre de blob directamente: {blob_name}")
            
        # Crear cliente para el blob
        blob_client = container_client.get_blob_client(blob_name)
        
        # Verificar si el blob existe
        logger.info(f"🔍 Verificando existencia del blob: {blob_name}")
        if not blob_client.exists():
            logger.error(f"❌ El blob {blob_name} no existe en el contenedor {AZURE_CONTAINER_NAME}")
            
            # Listar algunos blobs para debug
            try:
                logger.info(f"🔍 Listando hasta 5 blobs del contenedor como referencia:")
                count = 0
                for blob in container_client.list_blobs():
                    logger.info(f"📄 Blob encontrado: {blob.name}")
                    count += 1
                    if count >= 5:
                        break
                if count == 0:
                    logger.warning("⚠️ No se encontraron blobs en el contenedor")
            except Exception as e:
                logger.warning(f"⚠️ Error al listar blobs: {str(e)}")
                
            return None
        
        logger.info(f"✅ Blob {blob_name} encontrado")
        
        # Si no se proporciona local_path o está vacío, crear uno temporal
        if not local_path or local_path.strip() == "":
            # Crear directorio temporal
            temp_dir = "./temp_files"
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
                
            local_path = f"{temp_dir}/download_{uuid.uuid4()}_{os.path.basename(blob_name)}"
            logger.info(f"🔄 Creando ruta local automática: {local_path}")
            
        # Asegurarse de que el directorio existe
        try:
            os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
            logger.info(f"📁 Directorio para guardar creado: {os.path.dirname(os.path.abspath(local_path))}")
        except Exception as e:
            logger.error(f"❌ Error al crear directorio: {str(e)}")
            local_path = f"./temp_download_{uuid.uuid4()}_{os.path.basename(blob_name)}"
            logger.info(f"🔄 Usando ruta alternativa: {local_path}")
        
        logger.info(f"⬇️ Descargando blob a: {local_path}")
        
        # Descargar archivo
        with open(local_path, "wb") as download_file:
            download_data = blob_client.download_blob()
            download_file.write(download_data.readall())
            
        # Verificar que el archivo se descargó correctamente
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            logger.info(f"✅ Archivo descargado exitosamente a: {local_path} ({os.path.getsize(local_path)} bytes)")
            return local_path
        else:
            logger.error(f"❌ El archivo descargado está vacío o no existe: {local_path}")
            return None
        
    except ResourceNotFoundError as e:
        logger.error(f"❌ Recurso no encontrado en Azure: {str(e)}")
        return None
    except AzureError as e:
        logger.error(f"❌ Error de Azure: {str(e)}")
        is_azure_available = False  # Marcar como no disponible para futuros intentos
        return None
    except Exception as e:
        logger.error(f"❌ Error al descargar archivo de Azure Storage: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
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

def verify_azure_storage():
    """
    Verifica el estado de Azure Storage y reintenta la conexión si es necesario.
    
    Returns:
        bool: True si Azure Storage está disponible, False en caso contrario
    """
    global is_azure_available
    
    if is_azure_available:
        logger.info("✅ Azure Storage ya está disponible")
        return True
        
    logger.info("🔄 Intentando reconectar a Azure Storage...")
    return init_azure_storage()

# Verificar el estado cuando una solicitud llega desde endpoints críticos
async def ensure_azure_storage():
    """
    Asegura que Azure Storage esté disponible, reiniciando la conexión si es necesario.
    
    Returns:
        bool: True si Azure Storage está disponible, False en caso contrario
    """
    global is_azure_available
    
    if not is_azure_available:
        logger.warning("⚠️ Azure Storage no disponible, intentando reconectar...")
        if init_azure_storage():
            logger.info("✅ Reconexión a Azure Storage exitosa")
            return True
        else:
            logger.error("❌ No se pudo reconectar a Azure Storage")
            return False
    
    return True

def reset_connection():
    """
    Fuerza un reinicio de la conexión a Azure Storage independientemente del estado actual.
    
    Returns:
        bool: True si la conexión fue exitosa, False en caso contrario
    """
    global blob_service_client, container_client, is_azure_available
    
    # Reiniciar variables globales
    blob_service_client = None
    container_client = None
    is_azure_available = False
    
    logger.info("🔄 Reiniciando conexión a Azure Storage...")
    return init_azure_storage() 