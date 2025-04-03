from neo4j import GraphDatabase, Driver
from typing import List, Dict, Any, Optional
import logging
from config import (
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    NEO4J_MAX_RETRIES, NEO4J_RETRY_DELAY,
    NEO4J_MAX_CONNECTION_LIFETIME,
    NEO4J_MAX_CONNECTION_POOL_SIZE,
    NEO4J_CONNECTION_TIMEOUT,
    NEO4J_KEEP_ALIVE
)
import time
from neo4j.exceptions import ServiceUnavailable, SessionExpired
import os
import numpy as np
from .keys import NEO4J_URI_LOCAL, NEO4J_URI_PRODUCTION

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('neo4j_client.log')
    ]
)
logger = logging.getLogger(__name__)

class Neo4jClient:
    def __init__(self):
        # Determinar si estamos en producción o desarrollo
        self.is_production = os.getenv('ENVIRONMENT', 'development') == 'production'
        self.uri = NEO4J_URI_PRODUCTION if self.is_production else NEO4J_URI_LOCAL
        
        logger.info(f"Inicializando Neo4jClient en modo {'producción' if self.is_production else 'desarrollo'}")
        logger.info(f"URI de Neo4j: {self.uri}")
        
        self.driver = None
        self._connect()

    def _connect(self) -> None:
        """Establece la conexión con Neo4j"""
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
                max_connection_lifetime=3600,  # 1 hora para conexiones locales
                max_connection_pool_size=100,
                connection_timeout=10
            )
            logger.info(f"Conexión a Neo4j {'remota' if self.is_production else 'local'} establecida correctamente")
        except Exception as e:
            logger.error(f"Error al conectar con Neo4j: {str(e)}")
            raise

    def _verify_connection(self) -> bool:
        """Verifica la conexión con Neo4j y reintenta si es necesario."""
        if not self.driver:
            logger.warning("Driver no inicializado, intentando reconectar...")
            self._connect()
            return False

        for attempt in range(NEO4J_MAX_RETRIES):
            try:
                with self.driver.session() as session:
                    result = session.run("RETURN 1")
                    record = result.single()
                    if record and record[0] == 1:
                        logger.info("Conexión a Neo4j local verificada correctamente")
                        return True
            except Exception as e:
                logger.error(f"Error al verificar conexión (intento {attempt + 1}/{NEO4J_MAX_RETRIES}): {str(e)}")
                if attempt < NEO4J_MAX_RETRIES - 1:
                    time.sleep(NEO4J_RETRY_DELAY)
                    self._connect()
                else:
                    logger.error("No se pudo establecer conexión con Neo4j local después de varios intentos")
                    return False
        return False

    def _execute_query(self, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Ejecuta una consulta Cypher con manejo de errores y reintentos."""
        if not self._verify_connection():
            raise Exception("No se pudo establecer conexión con Neo4j local")

        for attempt in range(NEO4J_MAX_RETRIES):
            try:
                with self.driver.session() as session:
                    result = session.run(query, params or {})
                    return [dict(record) for record in result]
            except Exception as e:
                logger.error(f"Error al ejecutar consulta (intento {attempt + 1}/{NEO4J_MAX_RETRIES}): {str(e)}")
                if attempt < NEO4J_MAX_RETRIES - 1:
                    time.sleep(NEO4J_RETRY_DELAY)
                    self._connect()
                else:
                    raise

    def verify_user_credentials(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Verifica las credenciales del usuario."""
        query = """
        MATCH (u:User {email: $email})
        WHERE u.password = $password
        RETURN u
        """
        try:
            results = self._execute_query(query, {"email": email, "password": password})
            if results:
                return results[0]["u"]
            return None
        except Exception as e:
            logger.error(f"Error al verificar credenciales: {str(e)}")
            raise

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Obtiene un usuario por su email."""
        query = """
        MATCH (u:User {email: $email})
        RETURN u
        """
        try:
            results = self._execute_query(query, {"email": email})
            if results:
                return results[0]["u"]
            return None
        except Exception as e:
            logger.error(f"Error al obtener usuario por email: {str(e)}")
            raise

    def create_user_with_voice(self, username: str, email: str, password: str, voice_data: str = None, voice_embedding: list = None) -> Dict[str, Any]:
        """Crea un nuevo usuario con datos de voz."""
        logger.info(f"Creando usuario con voz: username={username}, email={email}, voice_embedding={'presente' if voice_embedding is not None else 'ausente'}")
        
        query = """
        CREATE (u:User {
            username: $username,
            email: $email,
            password: $password,
            voice_data: $voice_data,
            voice_embedding: $voice_embedding,
            created_at: datetime()
        })
        RETURN u
        """
        try:
            # Asegurarse de que el embedding sea una lista
            if voice_embedding is not None:
                if hasattr(voice_embedding, 'tolist'):
                    voice_embedding = voice_embedding.tolist()
                elif not isinstance(voice_embedding, list):
                    voice_embedding = list(voice_embedding)
                logger.info(f"Embedding convertido a lista, longitud: {len(voice_embedding)}")
            
            results = self._execute_query(query, {
                "username": username,
                "email": email,
                "password": password,
                "voice_data": voice_data,
                "voice_embedding": voice_embedding
            })
            
            if results:
                logger.info(f"Usuario creado exitosamente: {username} ({email})")
                return results[0]["u"]
            raise Exception("No se pudo crear el usuario")
        except Exception as e:
            logger.error(f"Error al crear usuario: {str(e)}")
            raise

    def close(self) -> None:
        """Cierra la conexión con Neo4j."""
        if self.driver:
            self.driver.close()
            logger.info("Conexión a Neo4j local cerrada")

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