from neo4j import GraphDatabase, Driver, Session
from keys import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from config import NEO4J_MAX_RETRIES, NEO4J_RETRY_DELAY
import logging
import hashlib
import time
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from typing import Optional, Dict, Any

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('neo4j.log')
    ]
)
logger = logging.getLogger(__name__)

class Neo4jClient:
    def __init__(self):
        self.driver: Optional[Driver] = None
        self._connect()

    def _connect(self):
        """Establece la conexión con Neo4j con reintentos"""
        logger.info("Iniciando conexión con Neo4j...")
        for attempt in range(NEO4J_MAX_RETRIES):
            try:
                logger.info(f"Intento de conexión {attempt + 1}/{NEO4J_MAX_RETRIES}")
                self.driver = GraphDatabase.driver(
                    NEO4J_URI,
                    auth=(NEO4J_USER, NEO4J_PASSWORD)
                )
                
                # Verificar la conexión
                with self.driver.session() as session:
                    result = session.run("RETURN 1")
                    result.single()
                    logger.info("Conexión con Neo4j establecida exitosamente")
                    return
                    
            except Exception as e:
                logger.error(f"Error en intento {attempt + 1}: {str(e)}")
                if attempt < NEO4J_MAX_RETRIES - 1:
                    logger.info(f"Reintentando en {NEO4J_RETRY_DELAY} segundos...")
                    time.sleep(NEO4J_RETRY_DELAY)
                else:
                    logger.error("No se pudo establecer conexión con Neo4j después de varios intentos")
                    raise
    
    def _verify_connection(self):
        """Verifica que la conexión esté activa y la restablece si es necesario"""
        try:
            if not self.driver:
                logger.warning("Driver de Neo4j no inicializado, reconectando...")
                self._connect()
            
            with self.driver.session() as session:
                result = session.run("RETURN 1")
                result.single()
                return True
        except Exception as e:
            logger.error(f"Error al verificar conexión: {str(e)}")
            logger.info("Intentando reconectar...")
            self._connect()
            return False
    
    def _execute_query(self, query: str, params: Dict[str, Any] = None) -> Any:
        """Ejecuta una consulta con manejo de errores y reintentos"""
        if not self._verify_connection():
            raise Exception("No se pudo establecer conexión con Neo4j")
        
        for attempt in range(NEO4J_MAX_RETRIES):
            try:
                logger.info(f"Ejecutando consulta (intento {attempt + 1}/{NEO4J_MAX_RETRIES})")
                with self.driver.session() as session:
                    result = session.run(query, params or {})
                    return result
            except Exception as e:
                logger.error(f"Error en consulta (intento {attempt + 1}): {str(e)}")
                if attempt < NEO4J_MAX_RETRIES - 1:
                    logger.info(f"Reintentando consulta en {NEO4J_RETRY_DELAY} segundos...")
                    time.sleep(NEO4J_RETRY_DELAY)
                    self._verify_connection()
                else:
                    raise
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Obtiene un usuario por su email"""
        logger.info(f"Buscando usuario con email: {email}")
        try:
            query = """
            MATCH (u:User {email: $email})
            RETURN u
            """
            result = self._execute_query(query, {"email": email})
            user = result.single()
            
            if user:
                logger.info(f"Usuario encontrado: {user['u']['username']}")
                return dict(user['u'])
            else:
                logger.info(f"No se encontró usuario con email: {email}")
                return None
                
        except Exception as e:
            logger.error(f"Error al buscar usuario: {str(e)}")
            raise
    
    def create_user_with_voice(self, username: str, email: str, password: str, 
                             voice_embedding: Any = None, voice_url: str = None) -> bool:
        """Crea un nuevo usuario con su embedding de voz"""
        logger.info(f"Creando usuario: {username} ({email})")
        try:
            query = """
            CREATE (u:User {
                username: $username,
                email: $email,
                password: $password,
                voice_embedding: $voice_embedding,
                voice_url: $voice_url,
                created_at: datetime()
            })
            RETURN u
            """
            
            params = {
                "username": username,
                "email": email,
                "password": password,
                "voice_embedding": voice_embedding.tolist() if voice_embedding is not None else None,
                "voice_url": voice_url
            }
            
            result = self._execute_query(query, params)
            user = result.single()
            
            if user:
                logger.info(f"Usuario creado exitosamente: {username}")
                return True
            else:
                logger.error("No se pudo crear el usuario")
                return False
                
        except Exception as e:
            logger.error(f"Error al crear usuario: {str(e)}")
            raise
    
    def verify_user_credentials(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Verifica las credenciales de un usuario"""
        logger.info(f"Verificando credenciales para: {email}")
        try:
            query = """
            MATCH (u:User {email: $email, password: $password})
            RETURN u
            """
            result = self._execute_query(query, {"email": email, "password": password})
            user = result.single()
            
            if user:
                logger.info(f"Credenciales válidas para: {email}")
                return dict(user['u'])
            else:
                logger.warning(f"Credenciales inválidas para: {email}")
                return None
                
        except Exception as e:
            logger.error(f"Error al verificar credenciales: {str(e)}")
            raise

    def close(self):
        """Cierra la conexión con Neo4j"""
        if self.driver:
            logger.info("Cerrando conexión con Neo4j...")
            self.driver.close()
            self.driver = None
            logger.info("Conexión cerrada")

    def create_user(self, username: str, email: str, password: str, voice_embedding: list = None):
        """Crea un nuevo usuario en la base de datos"""
        logger.info(f"Creando usuario: {username} ({email})")
        start_time = time.time()
        
        try:
            with self.driver.session() as session:
                # Verificar si el usuario ya existe
                result = session.run(
                    "MATCH (u:User {email: $email}) RETURN u",
                    email=email
                )
                if result.single():
                    logger.warning(f"Intento de crear usuario con email existente: {email}")
                    return False
                
                # Crear el usuario
                result = session.run(
                    """
                    CREATE (u:User {
                        username: $username,
                        email: $email,
                        password: $password,
                        created_at: datetime()
                    })
                    RETURN u
                    """,
                    username=username,
                    email=email,
                    password=password
                )
                
                if result.single():
                    logger.info(f"Usuario creado exitosamente: {username} ({email})")
                    process_time = time.time() - start_time
                    logger.debug(f"Tiempo de creación de usuario: {process_time:.2f}s")
                    return True
                else:
                    logger.error(f"Error al crear usuario: {username} ({email})")
                    return False
                    
        except Exception as e:
            logger.error(f"Error al crear usuario {username} ({email}): {str(e)}")
            return False

    def update_user_voice_embedding(self, email: str, voice_embedding: list):
        """Actualiza el embedding de voz de un usuario"""
        with self.driver.session() as session:
            try:
                query = """
                MATCH (u:User {email: $email})
                SET u.voice_embedding = $voice_embedding
                RETURN u {.*} as user
                """
                result = session.run(query, email=email, voice_embedding=voice_embedding)
                record = result.single()
                if record:
                    return record["user"]
                return None
            except Exception as e:
                logger.error(f"Error al actualizar embedding: {str(e)}")
                raise

    def update_user_voice_url(self, email: str, voice_url: str):
        """Actualiza la URL de la grabación de voz de un usuario"""
        with self.driver.session() as session:
            try:
                query = """
                MATCH (u:User {email: $email})
                SET u.voice_url = $voice_url
                RETURN u {.*} as user
                """
                result = session.run(query, email=email, voice_url=voice_url)
                record = result.single()
                if record:
                    return record["user"]
                return None
            except Exception as e:
                logger.error(f"Error al actualizar URL de voz: {str(e)}")
                raise

    def get_user_voice_embedding(self, email: str):
        """Obtiene el embedding de voz de un usuario"""
        with self.driver.session() as session:
            try:
                query = """
                MATCH (u:User {email: $email})
                RETURN u.voice_embedding as embedding
                """
                result = session.run(query, email=email)
                record = result.single()
                if record:
                    return record["embedding"]
                return None
            except Exception as e:
                logger.error(f"Error al obtener embedding: {str(e)}")
                raise

    def get_user_voice_url(self, email: str):
        """Obtiene la URL de la grabación de voz de un usuario"""
        with self.driver.session() as session:
            try:
                query = """
                MATCH (u:User {email: $email})
                RETURN u.voice_url as voice_url
                """
                result = session.run(query, email=email)
                record = result.single()
                if record:
                    return record["voice_url"]
                return None
            except Exception as e:
                logger.error(f"Error al obtener URL de voz: {str(e)}")
                raise 