from neo4j import GraphDatabase
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) # para agregar la carpeta padre al path y poder importar las keys
from keys import URI, USER, PASSWORD #Importo las credenciales de conexión desde mi archivo que contiene las keys

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

def get_neo4j_session():
    return driver.session()
