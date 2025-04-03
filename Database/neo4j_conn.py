from neo4j import GraphDatabase
import logging
from keys import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Neo4jConnection:
    def __init__(self):
        self._driver = None
        self._connect()

    def _connect(self):
        try:
            self._driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            logger.info("Conexión a Neo4j establecida correctamente")
        except Exception as e:
            logger.error(f"Error al conectar con Neo4j: {str(e)}")
            raise

    def close(self):
        if self._driver:
            self._driver.close()
            logger.info("Conexión a Neo4j cerrada")

    def get_driver(self):
        return self._driver

def get_neo4j_session():
    return driver.session()
