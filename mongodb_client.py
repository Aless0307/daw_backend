from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import logging
from keys import MONGODB_URI, DATABASE_NAME
from typing import Optional

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mongodb_client.log')
    ]
)
logger = logging.getLogger(__name__)

class MongoDBClient:
    _instance = None
    _client = None
    _db = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBClient, cls).__new__(cls)
            cls._instance._connect()
        return cls._instance

    def _connect(self):
        try:
            self._client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            self._db = self._client[DATABASE_NAME]
            # Verificar la conexión
            self._client.server_info()
            logger.info("Conexión a MongoDB establecida correctamente")
        except ServerSelectionTimeoutError as e:
            logger.error(f"Error al conectar con MongoDB: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error inesperado al conectar con MongoDB: {str(e)}")
            raise

    def get_db(self):
        return self._db

    def get_collection(self, collection_name):
        return self._db[collection_name]

    def create_user(self, username: str, email: str, password: str, voice_embedding: list = None, voice_url: str = None) -> bool:
        """
        Crea un nuevo usuario en la base de datos
        
        Args:
            username: Nombre del usuario
            email: Email del usuario
            password: Contraseña hasheada
            voice_embedding: Embedding de voz (opcional)
            voice_url: URL del archivo de voz (opcional)
            
        Returns:
            bool: True si el usuario fue creado exitosamente
        """
        try:
            logger.info(f"Creando usuario: {email}")
            
            # Verificar si el usuario ya existe
            if self.get_user_by_email(email):
                logger.warning(f"El usuario con email {email} ya existe")
                return False
            
            # Preparar datos del usuario
            user_data = {
                "username": username,
                "email": email,
                "password": password
            }
            
            # Agregar datos opcionales si existen
            if voice_embedding is not None:
                user_data["voice_embedding"] = voice_embedding
            if voice_url is not None:
                user_data["voice_url"] = voice_url
            
            # Insertar en la base de datos
            result = self._db.users.insert_one(user_data)
            
            if result.inserted_id:
                logger.info(f"Usuario creado exitosamente: {email}")
                return True
            else:
                logger.error(f"Error al crear usuario: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Error al crear usuario {email}: {str(e)}")
            return False

    def get_user_by_email(self, email: str) -> dict:
        """
        Obtiene un usuario por su email
        
        Args:
            email: Email del usuario a buscar
            
        Returns:
            dict: Datos del usuario o None si no existe
        """
        try:
            logger.info(f"Buscando usuario: {email}")
            user = self._db.users.find_one({"email": email})
            if user:
                logger.info(f"Usuario encontrado: {email}")
                return user
            else:
                logger.info(f"Usuario no encontrado: {email}")
                return None
        except Exception as e:
            logger.error(f"Error al buscar usuario {email}: {str(e)}")
            return None

    def update_user_voice(self, email: str, voice_embedding: list, voice_url: str = None) -> bool:
        """
        Actualiza los datos de voz de un usuario
        
        Args:
            email: Email del usuario
            voice_embedding: Nuevo embedding de voz
            voice_url: Nueva URL del archivo de voz (opcional)
            
        Returns:
            bool: True si la actualización fue exitosa
        """
        try:
            logger.info(f"Actualizando datos de voz para: {email}")
            
            # Preparar datos de actualización
            update_data = {
                "voice_embedding": voice_embedding
            }
            if voice_url is not None:
                update_data["voice_url"] = voice_url
            
            # Actualizar en la base de datos
            result = self._db.users.update_one(
                {"email": email},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"Datos de voz actualizados para: {email}")
                return True
            else:
                logger.warning(f"No se actualizaron datos de voz para: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Error al actualizar datos de voz para {email}: {str(e)}")
            return False

    def verify_user_credentials(self, email: str, password: str) -> dict:
        """
        Verifica las credenciales de un usuario
        
        Args:
            email: Email del usuario
            password: Contraseña hasheada
            
        Returns:
            dict: Datos del usuario si las credenciales son correctas, None en caso contrario
        """
        try:
            logger.info(f"Verificando credenciales para: {email}")
            user = self._db.users.find_one({
                "email": email,
                "password": password
            })
            
            if user:
                logger.info(f"Credenciales válidas para: {email}")
                return user
            else:
                logger.warning(f"Credenciales inválidas para: {email}")
                return None
                
        except Exception as e:
            logger.error(f"Error al verificar credenciales para {email}: {str(e)}")
            return None

    def find_user_by_voice(self, voice_embedding: list) -> Optional[dict]:
        """
        Busca un usuario por su embedding de voz.
        
        Args:
            voice_embedding (list): Embedding de voz a buscar
            
        Returns:
            Optional[dict]: Usuario encontrado o None
        """
        try:
            logger.info("Buscando usuario por voz")
            
            # Obtener todos los usuarios con embedding de voz
            users = self._db.users.find({"voice_embedding": {"$exists": True}})
            
            # Comparar con cada usuario
            for user in users:
                user_embedding = user["voice_embedding"]
                similarity = compare_voices(user_embedding, voice_embedding)
                
                if similarity >= VOICE_SIMILARITY_THRESHOLD:
                    logger.info(f"Usuario encontrado por voz: {user['email']}")
                    return user
            
            logger.info("No se encontró usuario con esa voz")
            return None
            
        except Exception as e:
            logger.error(f"Error al buscar usuario por voz: {str(e)}")
            raise 