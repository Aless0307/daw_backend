from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
import logging
import hashlib

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Neo4jClient:
    def __init__(self):
        self.driver = None
        self.connect()

    def connect(self):
        """Establece la conexión con Neo4j Aura"""
        try:
            logger.info(f"Conectando a Neo4j Aura: {NEO4J_URI}")
            self.driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            # Verificar conexión
            with self.driver.session() as session:
                result = session.run("RETURN 1 as num")
                record = result.single()
                if record and record["num"] == 1:
                    logger.info("Conexión exitosa con Neo4j Aura")
                else:
                    raise Exception("No se pudo verificar la conexión")
        except Exception as e:
            logger.error(f"Error al conectar con Neo4j Aura: {str(e)}")
            raise

    def close(self):
        """Cierra la conexión con Neo4j"""
        if self.driver:
            self.driver.close()
            logger.info("Conexión cerrada con Neo4j Aura")

    def create_user(self, username: str, email: str, password: str, voice_embedding: list = None):
        """Crea un nuevo usuario en la base de datos"""
        with self.driver.session() as session:
            try:
                query = """
                CREATE (u:User {
                    username: $username,
                    email: $email,
                    password: $password,
                    voice_embedding: $voice_embedding,
                    created_at: datetime()
                })
                RETURN id(u)
                """
                result = session.run(query, 
                          username=username,
                          email=email,
                          password=password,
                          voice_embedding=voice_embedding)
                record = result.single()
                user_id = record[0] if record else None
                logger.info(f"Usuario creado: {username} con ID {user_id}")
                return True
            except Exception as e:
                logger.error(f"Error al crear usuario: {str(e)}")
                raise

    def create_user_with_voice(self, username: str, email: str, password: str, voice_embedding: list = None, voice_url: str = None):
        """Crea un nuevo usuario con grabación de voz en la base de datos"""
        with self.driver.session() as session:
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
                RETURN id(u)
                """
                result = session.run(query, 
                          username=username,
                          email=email,
                          password=password,
                          voice_embedding=voice_embedding,
                          voice_url=voice_url)
                record = result.single()
                user_id = record[0] if record else None
                logger.info(f"Usuario creado con voz: {username} con ID {user_id}")
                return True
            except Exception as e:
                logger.error(f"Error al crear usuario con voz: {str(e)}")
                raise

    def get_user_by_email(self, email: str):
        """Obtiene un usuario por su email"""
        with self.driver.session() as session:
            try:
                query = """
                MATCH (u:User {email: $email})
                RETURN u {.*} as user
                """
                result = session.run(query, email=email)
                record = result.single()
                if record:
                    return record["user"]
                return None
            except Exception as e:
                logger.error(f"Error al obtener usuario: {str(e)}")
                raise

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

    def verify_user_credentials(self, email: str, password: str):
        """Verifica las credenciales de un usuario"""
        with self.driver.session() as session:
            try:
                # Obtener usuario por email
                query = """
                MATCH (u:User {email: $email})
                RETURN u {.*} as user
                """
                result = session.run(query, email=email)
                record = result.single()
                
                if not record:
                    logger.warning(f"Usuario no encontrado: {email}")
                    return None
                
                user = record["user"]
                stored_password = user.get("password", "")
                
                # Verificar contraseña hasheada
                hashed_password = hashlib.sha256(password.encode()).hexdigest()
                
                logger.info(f"Verificando credenciales para {email}")
                logger.debug(f"Stored hash: {stored_password[:10]}... Input hash: {hashed_password[:10]}...")
                
                if stored_password == hashed_password:
                    logger.info(f"Credenciales válidas para {email}")
                    return user
                else:
                    logger.warning(f"Contraseña incorrecta para {email}")
                    return None
                
            except Exception as e:
                logger.error(f"Error al verificar credenciales: {str(e)}")
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