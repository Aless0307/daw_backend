from neo4j import GraphDatabase
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) # para agregar la carpeta padre al path y poder importar las keys
from keys import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD #Importo las credenciales de conexión desde mi archivo que contiene las keys

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def get_neo4j_session():
    return driver.session()
