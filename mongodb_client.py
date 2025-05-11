import datetime
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import logging
from keys import MONGODB_URI, DATABASE_NAME
from typing import Optional
from config import VOICE_SIMILARITY_THRESHOLD
from bson import ObjectId # Importar ObjectId

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
            self._client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=15000) #lo aumento para el wifi del houtel
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

    def create_user(self, username: str, email: str, password: str, voice_embedding: list = None, voice_url: str = None, voice_embeddings: list = None, face_url: str = None) -> bool:
        """
        Crea un nuevo usuario en la base de datos
        
        Args:
            username: Nombre del usuario
            email: Email del usuario
            password: Contraseña hasheada
            voice_embedding: Embedding de voz individual (opcional)
            voice_url: URL del archivo de voz (opcional)
            voice_embeddings: Lista de embeddings de voz (opcional)
            face_url: URL de la foto de rostro (opcional)
            face_url_view: URL del visor de la foto de rostro (opcional)
            
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
            if voice_embeddings is not None:
                user_data["voice_embeddings"] = voice_embeddings
            if voice_url is not None:
                user_data["voice_url"] = voice_url
            if face_url is not None:
                user_data["face_url"] = face_url
            
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
            
            # Primero, buscar el usuario por email
            user = self._db.users.find_one({"email": email})
            
            if not user:
                logger.warning(f"Usuario no encontrado para el email: {email}")
                return None
                
            # Verificar la contraseña
            if user.get("password") == password:
                logger.info(f"Credenciales válidas para: {email}")
                return user
            else:
                logger.warning(f"Contraseña incorrecta para: {email}")
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
            # Importar localmente para evitar importación circular
            from voice_processing import compare_voices
            
            logger.info("Buscando usuario por voz")
            
            # Obtener todos los usuarios con embedding de voz (antiguo o nuevo formato)
            users = list(self._db.users.find({
                "$or": [
                    {"voice_embedding": {"$exists": True}},
                    {"voice_embeddings": {"$exists": True}}
                ]
            }))
            
            best_match = None
            best_similarity = 0
            
            # Comparar con cada usuario
            for user in users:
                max_similarity = 0
                
                # Verificar embeddings individuales si existen
                if "voice_embedding" in user:
                    user_embedding = user["voice_embedding"]
                    result = compare_voices(user_embedding, voice_embedding)
                    similarity = result.get("similarity", 0)
                    max_similarity = max(max_similarity, similarity)
                
                # Verificar galería de embeddings si existe
                if "voice_embeddings" in user and isinstance(user["voice_embeddings"], list):
                    for stored_embedding in user["voice_embeddings"]:
                        result = compare_voices(stored_embedding, voice_embedding)
                        similarity = result.get("similarity", 0)
                        max_similarity = max(max_similarity, similarity)
                
                # Actualizar mejor coincidencia si es necesario
                if max_similarity > best_similarity:
                    best_similarity = max_similarity
                    best_match = user
            
            # Verificar si la mejor coincidencia supera el umbral
            if best_match and best_similarity >= VOICE_SIMILARITY_THRESHOLD:
                logger.info(f"Usuario encontrado por voz: {best_match['email']} (similitud: {best_similarity:.4f})")
                return best_match
            
            logger.info("No se encontró usuario con esa voz")
            return None
            
        except Exception as e:
            logger.error(f"Error al buscar usuario por voz: {str(e)}")
            raise

    def update_user_voice_gallery(self, email: str, voice_embeddings: list, voice_url: str = None) -> bool:
        """
        Actualiza la galería de embeddings de voz de un usuario
        
        Args:
            email: Email del usuario
            voice_embeddings: Lista de embeddings de voz
            voice_url: Nueva URL del archivo de voz (opcional)
            
        Returns:
            bool: True si la actualización fue exitosa
        """
        try:
            logger.info(f"Actualizando galería de embeddings de voz para: {email}")
            
            # Preparar datos de actualización
            update_data = {
                "voice_embeddings": voice_embeddings
            }
            if voice_url is not None:
                update_data["voice_url"] = voice_url
            
            # Actualizar en la base de datos
            result = self._db.users.update_one(
                {"email": email},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"Galería de voz actualizada para: {email} con {len(voice_embeddings)} embeddings")
                return True
            else:
                logger.warning(f"No se actualizó la galería de voz para: {email}")
                return False
                
        except Exception as e:
            logger.error(f"Error al actualizar galería de voz para {email}: {str(e)}")
            return False

    def get_user_voice_data(self, email: str) -> dict:
        """
        Obtiene los datos de voz de un usuario
        
        Args:
            email: Email del usuario
            
        Returns:
            dict: Datos de voz del usuario (embeddings y URL) o None si no existen
        """
        try:
            logger.info(f"Obteniendo datos de voz para: {email}")
            
            # Buscar usuario
            user = self._db.users.find_one(
                {"email": email},
                {"voice_embedding": 1, "voice_embeddings": 1, "voice_url": 1, "_id": 0}
            )
            
            if not user:
                logger.warning(f"Usuario no encontrado: {email}")
                return None
                
            return user
                
        except Exception as e:
            logger.error(f"Error al obtener datos de voz para {email}: {str(e)}")
            return None 
        
        # Tu get_current_user retorna el dict completo, lo cual es bueno, pero tener get_user_by_id puede ser útil.
    def get_user_by_id(self, user_id: ObjectId) -> Optional[dict]:
         """Obtiene un usuario por su ObjectId."""
         try:
             logger.debug(f"Buscando usuario por ID: {user_id}")
             user = self._db.users.find_one({"_id": user_id})
             # No loguear el usuario completo por seguridad
             if user:
                 logger.debug(f"Usuario encontrado por ID: {user_id}")
             else:
                 logger.debug(f"Usuario no encontrado por ID: {user_id}")
             return user
         except Exception as e:
             logger.error(f"Error al buscar usuario por ID {user_id}: {str(e)}")
             return None


    # --- NUEVOS MÉTODOS PARA LA LÓGICA ---

    def get_random_unsolved_problem(self, user_id: ObjectId, difficulty: Optional[str] = None) -> Optional[dict]:
        """
        Busca un problema aleatorio que el usuario no haya resuelto, opcionalmente filtrado por dificultad.

        Args:
            user_id: El ObjectId del usuario.
            difficulty: Dificultad del problema a buscar (ej. "basico", "intermedio", "avanzado").

        Returns:
            dict: Un documento de problema (con _id, text, difficulty) o None si no hay problemas sin resolver.
        """
        try:
            # --- Añadir Logging de entrada ---
            logger.info(f"[{user_id}] Inicio get_random_unsolved_problem. Dificultad solicitada: {difficulty}")

            # 1. Obtener los IDs de los problemas que el usuario ya resolvió
            user_doc = self._db.users.find_one(
                {"_id": user_id},
                {"ejercicios": 1} # Solo necesitamos el array de ejercicios resueltos
            )
            solved_problem_ids = []
            if user_doc and user_doc.get("ejercicios"):
                solved_problem_ids = [
                    exercise["problem_id"]
                    for exercise in user_doc["ejercicios"]
                    if isinstance(exercise, dict) and "problem_id" in exercise and isinstance(exercise["problem_id"], ObjectId)
                    # Asegurarse de que es un dict y tiene un problem_id que es un ObjectId
                ]
            # --- Añadir Logging de IDs resueltos ---
            logger.debug(f"[{user_id}] Problemas resueltos encontrados: {len(solved_problem_ids)} IDs")
            if solved_problem_ids:
                # Loguear solo algunos IDs si la lista es muy larga
                    logger.debug(f"[{user_id}] Primeros 5 IDs resueltos: {solved_problem_ids[:5]}")


            # 2. Construir el filtro para la colección de problemas
            problem_filter = {}
            if difficulty:
                problem_filter["difficulty"] = difficulty

            # Excluir los problemas que ya ha resuelto el usuario
            # La condición es: "_id no debe estar en la lista de solved_problem_ids"
            problem_filter["_id"] = {"$nin": solved_problem_ids}

            # --- Añadir Logging del filtro ---
            logger.debug(f"[{user_id}] Filtro final para la colección 'ejercicios': {problem_filter}")


            # 3. Buscar un problema aleatorio que coincida con el filtro
            # Usar el pipeline de agregación con $sample para obtener un documento aleatorio
            pipeline = [
                {"$match": problem_filter},
                {"$sample": {"size": 1}} # Obtener 1 documento aleatorio del resultado del $match
                # Opcional: Añadir un $project si quieres limitar los campos devueltos
                # {"$project": {"text": 1, "difficulty": 1, "topics": 1}}
            ]

            # Ejecutar la agregación en la colección de problemas (ejercicios)
            problem_collection = self._db.ejercicios # Asumiendo que la colección de problemas se llama 'ejercicios'

            # --- Añadir Logging del pipeline ---
            logger.debug(f"[{user_id}] Pipeline de agregación: {pipeline}")

            result = list(problem_collection.aggregate(pipeline))

            # --- Añadir Logging del resultado de la agregación ---
            logger.debug(f"[{user_id}] Resultado de la agregación: {result}")


            if result:
                logger.info(f"[{user_id}] Problema sin resolver encontrado: {result[0].get('_id')} (Dificultad: {result[0].get('difficulty')})")
                # Devolver el primer (y único) documento del resultado de $sample
                return result[0]
            else:
                # Este es el caso que te está ocurriendo
                logger.warning(f"[{user_id}] No se encontraron problemas sin resolver con el filtro especificado. El resultado de la agregación está vacío.")
                return None # No hay problemas que coincidan con los criterios y no estén resueltos

        except Exception as e:
            # --- Añadir Logging de error ---
            logger.error(f"[{user_id}] ERROR en get_random_unsolved_problem: {str(e)}", exc_info=True) # exc_info=True para stack trace
            # Dependiendo de tu estrategia de manejo de errores, podrías relanzar
            # raise # Si quieres que el error llegue al cliente como 500
            return None # Si prefieres que el endpoint retorne None o un mensaje amigable

    def add_solved_exercise(self, user_id: ObjectId, exercise_data: dict) -> Optional[object]: # Cambiado tipo de retorno
        """
        Añade un ejercicio resuelto al array 'ejercicios' del usuario.
        Devuelve el objeto UpdateResult de pymongo o None en caso de error.
        """
        try:
            logger.info(f"Añadiendo ejercicio resuelto para user_id: {user_id}")
            if not isinstance(exercise_data.get("problem_id"), ObjectId):
                 logger.error(f"exercise_data: 'problem_id' debe ser ObjectId.")
                 return None # Devolver None en error de validación
            if not exercise_data.get("problem_difficulty"):
                 logger.error("exercise_data: 'problem_difficulty' requerido.")
                 return None # Devolver None en error de validación

            # --- CORRECCIÓN VALIDACIÓN TIMESTAMP ---
            # Validar timestamp de forma más simple y segura
            ts = exercise_data.get("timestamp")
            if ts is not None and not isinstance(ts, datetime):
                 logger.warning(f"'timestamp' en exercise_data no es datetime: {type(ts)}. Se espera datetime o None.")
                 # Podrías decidir quitarlo o convertirlo si es posible, o simplemente loguear.
                 # Por ahora, solo logueamos la advertencia.
            # --- FIN CORRECCIÓN ---

            # --- CORRECCIÓN VALOR DE RETORNO ---
            # Ejecutar update y DEVOLVER el resultado directamente
            result = self._db.users.update_one(
                {"_id": user_id},
                {"$push": {"ejercicios": exercise_data}}
            )
            # Ya no retornamos True/False, retornamos el objeto 'result'
            return result
            # --- FIN CORRECCIÓN ---

        except Exception as e:
            logger.error(f"Error al añadir ejercicio resuelto para user_id {user_id}: {str(e)}")
            return None # Devolver None en caso de excepción de DB
        

    def get_problem_by_id(self, problem_id: ObjectId) -> dict | None:
        """Busca un problema por su ObjectId en la colección 'ejercicios'."""
        # Acceder a la colección a través de self._db
        collection_name = 'ejercicios' # Nombre de la colección de problemas
        if self._db is None:
             logger.error(f"MongoDBClient: La conexión a la base de datos (self._db) no está disponible al buscar problema {problem_id}.")
             return None

        logger.info(f"MONGO_CLIENT: Buscando problema con _id: {problem_id} en colección '{collection_name}'")
        try:
            # --- CORRECCIÓN: Usar self._db['nombre_coleccion'] ---
            problem_collection = self._db[collection_name]
            problem = problem_collection.find_one({"_id": problem_id})
            # --- FIN CORRECCIÓN ---

            if problem:
                 logger.info(f"MONGO_CLIENT: Problema encontrado para ID {problem_id}")
            else:
                 logger.warning(f"MONGO_CLIENT: Problema con _id {problem_id} no encontrado en la colección '{collection_name}'.")
            return problem # Devuelve el documento (dict) o None
        except Exception as e:
             logger.error(f"MONGO_CLIENT: Error en get_problem_by_id buscando ID {problem_id}: {e}", exc_info=True)
             return None # Devuelve None en caso de error de DB