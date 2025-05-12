# routers/logic.py

from fastapi import APIRouter, Depends, HTTPException, status, Query, Form # Importa Form si esperas datos de formulario
from fastapi.responses import Response
from bson import ObjectId
from typing import Optional, Dict, List, Union, Annotated # Importa Annotated
from datetime import datetime # Para el timestamp
import logging
import asyncio # Necesario para asyncio.to_thread para llamadas síncronas a DB

# Importa cliente Google Cloud Text-to-Speech si lo usas (ya debe estar)
from google.cloud import texttospeech

# Importa tu cliente de MongoDB
from mongodb_client import MongoDBClient

# Importa tu dependencia de autenticación
from utils.auth_utils import get_current_user

from models.logic import UserProgressResponse, DifficultyProgress, ProblemResponse, NoProblemResponse, FeedbackResponse, TTSTextRequest # Asegúrate de que FeedbackResponse esté en models.logic

from google.oauth2 import service_account # Asegúrate de que esto esté importado

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --- Configuración para el LLM (Gemini) ---
# Necesitas una función que llame a la API de Gemini.
# Supondremos que tienes un archivo como utils/gemini_utils.py
# con una función get_gemini_feedback(problem_text: str, user_answer: str) -> Dict[str, Any] (o None si falla).
# Esta función debería llamar a la API de Gemini con un prompt adecuado.
try:
    # ASEGÚRATE de que la ruta de importación sea correcta para tu proyecto
    # y que el archivo utils/gemini_utils.py exista y tenga la función get_gemini_feedback
    from utils.gemini_utils import get_gemini_feedback
    GEMINI_AVAILABLE = True
    logger.info("Módulo gemini_utils importado correctamente.")
except ImportError:
    logger.warning("Módulo gemini_utils no encontrado o get_gemini_feedback no definido. La evaluación usará placeholders.")
    GEMINI_AVAILABLE = False
    # Definir una función placeholder async si no existe la real, para evitar errores
    async def get_gemini_feedback(problem_text: str, user_answer: str):
        logger.warning("Usando placeholder get_gemini_feedback.")
        # Simulación de respuesta de Gemini (debe coincidir con el formato esperado)
        simulated_analysis = f"Análisis simulado para '{user_answer[:50]}...'. Parece una respuesta con longitud {len(user_answer)}. (Evaluación Simulada)"
        simulated_grade = max(0, min(10, len(user_answer) // 5)) # Simulación simple de nota 0-10
        # Simular algo de latencia
        await asyncio.sleep(1)
        return {"analysis": simulated_analysis, "grade": simulated_grade}


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/logic", # Prefijo /logic para este router
    tags=["Logic Problems"],
    # dependencies=[Depends(get_current_user)] # Opcional: Proteger todo el router
)

# Instancia del Cliente MongoDB (asumiendo que ya la tienes)
try:
    mongo_client = MongoDBClient()
    logger.info("MongoDBClient instanciado en routers/logic.py")
except Exception as e:
    logger.error(f"Error al instanciar MongoDBClient en routers/logic.py: {e}")
    mongo_client = None # Set a None si falla para verificar en endpoints

# Instancia del cliente Google Cloud Text-to-Speech (asumiendo que ya la tienes e inicializaste)
SERVICE_ACCOUNT_KEY_PATH = "/home/alessandro_hp/Documentos/Cursor/DAW_PROYECTO/daw_backend/scripts/daw-proyecto-458721-accdda2dde3a.json" # <-- Tu ruta exacta

# Instancia del cliente Google Cloud Text-to-Speech (inicializar al inicio del módulo)
tts_client = None # Inicializar a None
# Aseguramos que la variable credentials también se inicialice a None aquí
credentials = None
try:
    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_KEY_PATH)

    logger.info(f"Credenciales cargadas desde archivo type: {type(credentials)}, value: {credentials}")
    # ----------------------------------------------------
    tts_client = texttospeech.TextToSpeechClient(credentials=credentials) # <-- ¡¡PASAR LA VARIABLE credentials!!

    logger.info(f"Cliente Google Cloud Text-to-Speech inicializado usando archivo explícito: {SERVICE_ACCOUNT_KEY_PATH}")

# Capturar errores específicos de archivo no encontrado primero
except FileNotFoundError:
    logger.error(f"Error: Archivo de clave de cuenta de servicio NO ENCONTRADO en la ruta: {SERVICE_ACCOUNT_KEY_PATH}", exc_info=True)
    tts_client = None
    credentials = None
except Exception as e:
    # Capturar cualquier otro error durante la inicialización (archivo inválido, permisos, red, etc.)
    logger.error(f"Error al inicializar cliente Google Cloud TTS con archivo {SERVICE_ACCOUNT_KEY_PATH}: {str(e)}", exc_info=True)
    tts_client = None
    credentials = None

logger.info(f"Estado final de tts_client después de la inicialización del módulo: {type(tts_client)}")
# ---------------------------------------------------


# --- Endpoint de Progreso ---
@router.get(
    "/progress",
    response_model=UserProgressResponse,
    summary="Obtiene el progreso del usuario autenticado"
)
async def get_user_progress(
    current_db_user: Annotated[dict, Depends(get_current_user)]
):
    if mongo_client is None:
         raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Servicio de base de datos no disponible.")

    user_id = current_db_user.get("_id"); user_email = current_db_user.get("email", "N/A")

    if not user_id or not isinstance(user_id, ObjectId):
         # Esto no debería pasar si get_current_user funciona bien, pero es una seguridad.
         logger.error(f"Dependencia get_current_user no devolvió un _id ObjectId válido para {user_email}")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al obtener datos de usuario.")

    logger.info(f"Solicitud de progreso para usuario: {user_email} (ID: {user_id})")

    # El array de ejercicios resueltos está directamente en el documento del usuario
    solved_exercises = current_db_user.get("ejercicios", []) # Acceder directamente al array del documento proporcionado por el Depends

    # Lógica de Cálculo (sin cambios)...
    progress_counts: Dict[str, int] = {"basico": 0, "intermedio": 0, "avanzado": 0}
    progress_sums: Dict[str, float] = {"basico": 0.0, "intermedio": 0.0, "avanzado": 0.0}
    total_solved_count = 0; total_grade_sum = 0.0
    for exercise in solved_exercises:
        if isinstance(exercise, dict) and exercise.get("problem_difficulty") in progress_counts and isinstance(exercise.get("llm_grade"), (int, float)):
            difficulty = exercise["problem_difficulty"]; grade = exercise["llm_grade"]
            total_solved_count += 1; total_grade_sum += grade
            progress_counts[difficulty] += 1; progress_sums[difficulty] += grade
        else: logger.warning(f"Ejercicio formato inválido user_id {user_id}: {exercise}")
    progress_by_difficulty: Dict[str, DifficultyProgress] = {}
    for dl in ["basico", "intermedio", "avanzado"]:
        count = progress_counts[dl]; grade_sum = progress_sums[dl]
        avg_grade = round(grade_sum / count, 2) if count > 0 else 0.0
        progress_by_difficulty[dl] = DifficultyProgress(solved_count=count, average_grade=avg_grade)
    overall_avg = round(total_grade_sum / total_solved_count, 2) if total_solved_count > 0 else 0.0
    logger.info(f"Progreso calculado para {user_email}: Total={total_solved_count}, Avg={overall_avg}")
    return UserProgressResponse(total_solved=total_solved_count, progress_by_difficulty=progress_by_difficulty, overall_average_grade=overall_avg, message="Tu progreso ha sido cargado.")


# --- Endpoint para Obtener Problema ---
@router.get(
    "/problem",
    response_model=Union[ProblemResponse, NoProblemResponse],
    summary="Obtiene un problema de lógica no resuelto"
)
async def get_logic_problem(
    current_db_user: Annotated[dict, Depends(get_current_user)],
    difficulty: Annotated[str | None, Query(description="Filtrar por dificultad")] = None
):
    if mongo_client is None: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Servicio DB no disponible.")
    user_id = current_db_user.get("_id"); user_email = current_db_user.get("email", "N/A")
    if not user_id or not isinstance(user_id, ObjectId): raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="ID usuario inválido.")
    if difficulty is not None and difficulty not in ["basico", "intermedio", "avanzado"]: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dificultad inválida.")
    logger.info(f"Buscando problema user_id: {user_id}, dificultad: {difficulty or 'cualquiera'}")

    try:
        problem_dict = await asyncio.to_thread(mongo_client.get_random_unsolved_problem, user_id, difficulty=difficulty)

    except Exception as db_error:
        logger.error(f"Error DB consulta problemas user {user_id}: {db_error}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error DB consulta problemas.")

    if problem_dict:
        logger.info(f"Problema encontrado {user_email}: ID={problem_dict.get('_id')}")
        try:
             # Crear instancia Pydantic explícitamente para validación y serialización
             validated_problem = ProblemResponse(id=str(problem_dict["_id"]), text=problem_dict["text"], difficulty=problem_dict["difficulty"], topics=problem_dict.get("topics", []))
             return validated_problem
        except Exception as e:
             logger.error(f"Error procesando datos problema {problem_dict.get('_id')} para {user_email}: {e}", exc_info=True)
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error procesando datos problema.")
    else:
        logger.info(f"No se encontraron problemas {user_email}, dificultad: {difficulty or 'cualquiera'}")
        message = f"¡Felicidades! Has resuelto todos los problemas de nivel '{difficulty}'." if difficulty else "¡Felicidades! Has resuelto todos los problemas."
        return NoProblemResponse(message=message)


# --- Endpoint POST /tts 
@router.post("/tts")
async def text_to_speech(
    # --- CAMBIO AQUÍ ---
    # Ahora FastAPI espera un cuerpo JSON que coincida con el modelo TTSTextRequest
    request_data: TTSTextRequest, # <-- Usamos el modelo Pydantic para el cuerpo
    # --- FIN CAMBIO ---
    current_user: Annotated[dict, Depends(get_current_user)] # Proteger el endpoint
):
    if not tts_client:
        logger.error("Intento de usar TTS, pero cliente no inicializado.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Servicio de voz no disponible en el servidor.")

    # Obtener el texto del objeto recibido del frontend
    text = request_data.text # <-- Acceder al texto desde el objeto request_data

    if not text: # Esta verificación aún es útil si el modelo permitiera texto vacío, pero el modelo BaseModel no lo permite por defecto
        logger.warning(f"Solicitud /tts con texto vacío de usuario {current_user.get('email', 'N/A')}")
        # FastAPI ya manejaría esto con 422 si el modelo requiriera texto no vacío, pero la dejamos por claridad.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se proporcionó texto para convertir a voz.")

    user_email = current_user.get("email", "N/A")
    logger.info(f"Generando voz para usuario {user_email}: '{text[:50]}...'")

    try:
        # ... (resto del código para llamar a synthesize_speech con el 'text' obtenido) ...
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(language_code="es-MX", ssml_gender=texttospeech.SsmlVoiceGender.FEMALE) # Configurar voz estándar
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3) # Configurar audio MP3

        response = tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )

        logger.info(f"Voz generada exitosamente para {user_email} ({len(response.audio_content)} bytes).")
        return Response(content=response.audio_content, media_type="audio/mpeg")

    except Exception as e:
        logger.error(f"Error durante la síntesis de voz con Google Cloud TTS para {user_email}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al generar voz en el servidor: {str(e)}")


# --- Endpoint para Enviar Respuesta (CONEXIÓN CON LLM Y SAVE RESULT) ---
# Este endpoint recibe el texto de la respuesta, la evalúa y la guarda.
# REQUIERE que tengas implementada la función get_gemini_feedback en utils/gemini_utils.py
# REQUIERE que add_solved_exercise en mongodb_client.py funcione correctamente.
@router.post(
    "/submit_answer",
    # Asumiendo que models/logic.py tiene un modelo FeedbackResponse
    # con al menos 'analysis' (str) y 'grade' (int o float).
    # Ejemplo: class FeedbackResponse(BaseModel): analysis: str; grade: int
    response_model=FeedbackResponse,
    summary="Recibe respuesta, evalúa con IA y guarda el resultado",
)
async def submit_user_answer(
    # current_user es el documento del usuario logeado, ya obtenido por Depends
    current_db_user: Annotated[dict, Depends(get_current_user)],
    problem_id: Annotated[str, Form(...)], # Recibe el ID del problema (como string) del frontend (Form data)
    user_answer: Annotated[str, Form(...)] # Recibe el texto de la respuesta (como string) del frontend (Form data)
):
    if mongo_client is None:
         raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Servicio de base de datos no disponible.")

    user_id = current_db_user.get("_id"); user_email = current_db_user.get("email", "N/A")
    if not user_id or not isinstance(user_id, ObjectId):
         # Esto no debería pasar con un Depends válido, pero es una seguridad
         logger.error(f"Dependencia get_current_user no devolvió un _id ObjectId válido para {user_email}")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al obtener datos de usuario.")

    # 1. Validar y convertir el ID del problema recibido
    try:
        # problem_id llega como string del frontend (Form data)
        problem_id_obj = ObjectId(problem_id) # Convertir el string ID a ObjectId
    except Exception:
        # Si la conversión falla, el ID recibido no es válido
        logger.warning(f"ID de problema inválido recibido de {user_email}: '{problem_id}'")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de problema inválido.")

    logger.info(f"Usuario '{user_email}' (ID: {user_id}) envió respuesta para problema '{problem_id_obj}'.")
    logger.debug(f"Respuesta recibida: '{user_answer}'")

    # 2. Obtener el problema original de la DB (necesario para el prompt del LLM)
    # Asumiendo que tienes un método get_problem_by_id(problem_id_obj) en mongo_client
    try:
        # Si get_problem_by_id es síncrono (PyMongo), usa asyncio.to_thread
        # Si es async (Motor), quita await asyncio.to_thread
        problem_data = await asyncio.to_thread(mongo_client.get_problem_by_id, problem_id_obj)
        # Si no tienes get_problem_by_id, puedes intentar obtenerlo de la misma agregación que en get_random_unsolved_problem,
        # pero get_problem_by_id es más limpio. Implementa get_problem_by_id en mongo_client si no existe.
    except Exception as db_error:
        logger.error(f"Error DB al obtener problema {problem_id_obj} para {user_email}: {db_error}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al validar el problema.")

    if not problem_data:
        logger.warning(f"Problema {problem_id_obj} no encontrado en DB para respuesta de {user_email}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El problema especificado no fue encontrado.")

    # 3. --- PREPARAR PROMPT PARA LLM ---
    # Aquí es donde construirías el prompt para el LLM, incluyendo:
    # - Contexto general del proyecto (aplicación educativa, para usuarios ciegos, etc.)
    # - Progreso del usuario (opcional, pero útil para contexto del LLM)
    # - El problema original (problem_data['text'])
    # - La respuesta del usuario (user_answer)
    # - Instrucciones claras para el LLM (analizar lógica, no código, calificar 1-5, formato JSON).

    # Para obtener el progreso del usuario *actualizado* para el prompt,
    # podrías volver a calcularlo o obtener el documento completo de usuario.
    # El current_db_user ya trae el array 'ejercicios'.
    # Puedes reutilizar la lógica de cálculo de progreso de get_user_progress aquí.

    user_solved_exercises = current_db_user.get("ejercicios", []) # Array de ejercicios resueltos
    # Calcula el progreso actual (total, por dificultad, promedios) a partir de user_solved_exercises

    # --- Simulación de cálculo de progreso para el prompt ---
    # NOTA: Reemplaza esto con la lógica real de cálculo de progreso si la necesitas en el prompt.
    total_solved_count = len(user_solved_exercises)
    # Aquí iría la lógica para calcular promedios y conteos por dificultad si los incluyes en el prompt.
    # --- Fin Simulación ---


    # --- Construir el prompt ---
    # Este prompt es CRUCIAL para guiar al LLM. Adapta el texto según el modelo LLM que uses.
    llm_prompt_parts = [
        "SISTEMA: Eres un tutor de lógica de programación, amigable y servicial, especializado en ayudar a usuarios ciegos que están aprendiendo a programar. Tu retroalimentación debe centrarse en los pasos lógicos, el enfoque de resolución de problemas, la corrección y la eficiencia, no en la sintaxis específica del código. Proporciona un análisis claro y asigna una calificación.",
        "CONTEXTO: Esta es una aplicación web educativa para personas ciegas. La interacción es principalmente a través de la voz. Tu respuesta será leída en voz alta por un lector de pantalla.",
        f"RESUMEN_PROGRESO_USUARIO: Este usuario ha resuelto {total_solved_count} ejercicios hasta ahora.", # Puedes añadir más detalles aquí si los calculaste
        f"PROBLEMA_LOGICA_PROGRAMACION: {problem_data['text']}", # El enunciado original del problema
        f"LOGICA_SOLUCION_ENVIADA_USUARIO: {user_answer}", # La respuesta transcrita del usuario
        "INSTRUCCIONES: Basándote en el PROBLEMA_LOGICA_PROGRAMACION y la LOGICA_SOLUCION_ENVIADA_USUARIO:",
        "- Analiza la lógica y el proceso de pensamiento propuestos por el usuario. ¿Es un enfoque válido para resolver el problema?",
        "- Comenta sobre su corrección, claridad y eficiencia potencial. Discute casos límite si son relevantes para el problema.",
        "- NO proporciones fragmentos de código ni sintaxis de código específica en tu análisis.",
        "- trata de escribirlo correctamente para que el text to speech lo lea bien, ya que si pones simbolos o caracteres raros, el lector de pantalla no lo leerá bien y puede confundir al usuario ciego.",
        "- no seas muy estricto, pero si hazle saber si se equivocó o faltó información.",
        "- Proporciona retroalimentación detallada (apunta a 20-200 palabras, mantenla concisa pero informativa para la voz).",
        "- El usuario es ciego, por ende no esperes que te brinde código o pseudocódigo, sino una explicación de su razonamiento. Sólo evalúa la lógica de su respuesta, no la sintaxis.",
        "- no uses el símbolo '' para indicar comillas, ya que el lector de pantalla no lo leerá bien.",
        "- El speech to text entiende ford en vez de for, entonces cuando te diga ford, entiende que es for.",
        "- No utilices comillas simples ni dobles, ya que el lector de pantalla no lo leerá bien.",
        "- Si vas a brindar ejemplos con símvolos así como * - / + - =, adapta el contenido para que el lector de pantalla lo lea bien, usa palabras en vez de ciertos símbolos, los que consideres que el tts, no leerá bien, piensa la respuesta que darás, ya que todas serán procesadas con él lector de pantalla.",
        "- Asigna una calificación para la lógica de la solución en una escala de 0 a 10, donde 0 es completamente incorrecto/sin intento, y 10 es excelente.",
        "- Responde ÚNICAMENTE en formato JSON con las claves 'analysis' (cadena de texto) y 'grade' (entero de 0 a 10). Asegúrate de que el JSON sea válido.",
        # Mantuve el contenido del análisis en inglés como ejemplo, pero tu LLM debería generarlo en español
        "EXAMPLE_JSON_RESPONSE: {\"analysis\": \"Your approach is logical and correct... but could be more efficient by...\", \"grade\": 8}"
    ]
    llm_prompt = "\n".join(llm_prompt_parts)

    # 4. --- LLAMADA AL LLM ---
    llm_analysis = "Análisis no disponible (servicio de IA no configurado o falló)."
    llm_grade = 0 # Grado por defecto si falla el LLM

    if GEMINI_AVAILABLE:
        logger.info(f"Llamando a Gemini para evaluar respuesta del problema {problem_id_obj} para user {user_email}...")
        try:
            # La función get_gemini_feedback debe estar implementada en utils/gemini_utils.py
            # y ser ASYNC (def async) para usar await aquí.
            # Si es SÍNCRONA, usa: feedback_result = await asyncio.to_thread(get_gemini_feedback, ...)
            feedback_result = await get_gemini_feedback(problem_data['text'], user_answer)
            

            if feedback_result and isinstance(feedback_result, dict): # Verificar que sea un diccionario
                llm_analysis = feedback_result.get("analysis", "Error al extraer análisis del resultado de IA.")
                try:
                     # Intentar convertir la calificación a entero, manejando posibles errores
                     llm_grade = int(feedback_result.get("grade", 0))
                     # Asegurar que la calificación esté en el rango esperado (ej. 0-10)
                     llm_grade = max(0, min(10, llm_grade))
                except (ValueError, TypeError):
                     logger.error(f"Nota inválida recibida de Gemini para {user_email} ({problem_id_obj}): '{feedback_result.get('grade')}'. Usando 0.")
                     llm_grade = 0
                logger.info(f"Evaluación de Gemini recibida para {user_email}: Calificación={llm_grade}")
            else:
                logger.error(f"La llamada a Gemini no devolvió un diccionario o falló para {user_email} ({problem_id_obj}). Resultado: {feedback_result}")
                llm_analysis = "La evaluación automática falló. Intenta de nuevo más tarde." # Mensaje amigable si el LLM falla
                llm_grade = 0 # Calificación por defecto si falla el LLM
        except Exception as llm_error:
            # Capturar errores durante la llamada o procesamiento de la respuesta de Gemini
            logger.error(f"Error inesperado durante la llamada o procesamiento de Gemini para {user_email} ({problem_id_obj}): {llm_error}", exc_info=True)
            llm_analysis = "Error interno al procesar la evaluación automática. Intenta de nuevo." # Mensaje amigable si el LLM falla
            llm_grade = 0 # Calificación por defecto si falla el LLM
    else:
        # Lógica placeholder si Gemini no está disponible (definida arriba en el try/except de importación)
        # get_gemini_feedback ya es la función placeholder si la importación falla
        logger.warning("Usando evaluación placeholder porque Gemini no está disponible.")
        # Llamamos al placeholder para generar un resultado simulado
        simulated_feedback = await get_gemini_feedback(problem_data['text'], user_answer)
        llm_analysis = simulated_feedback["analysis"]
        llm_grade = simulated_feedback["grade"]


    # 5. --- GUARDAR RESULTADO EN DB ---
    # Preparamos los datos para guardar en el array 'ejercicios' del usuario
    submission_data = {
        "problem_id": problem_id_obj, # ID del problema (ObjectId)
        "problem_difficulty": problem_data.get("difficulty", "desconocida"), # Dificultad del problema original
        "user_answer": user_answer, # La respuesta del usuario (texto)
        "analysis_received": llm_analysis, # El análisis del LLM
        "llm_grade": llm_grade, # La calificación del LLM (0-10)
        "submission_timestamp": datetime.utcnow() # Timestamp de la sumisión
    }

    save_error = False
    try:
        # Llamar al método add_solved_exercise de MongoDBClient para guardar
        # Asumiendo que add_solved_exercise es síncrono (PyMongo), usar asyncio.to_thread
        # Si es async (Motor), quitar await asyncio.to_thread
        update_result = await asyncio.to_thread(mongo_client.add_solved_exercise, user_id, submission_data)

        # Verificar el resultado de la operación de guardado (opcional pero recomendado)
        # add_solved_exercise debería devolver UpdateResult si usa update_one
        if update_result is None:
            save_error = True
            logger.error(f"La función add_solved_exercise devolvió None para user {user_id}. No se pudo guardar.")
        elif hasattr(update_result, 'matched_count') and hasattr(update_result, 'modified_count'):
             if update_result.matched_count == 0:
                  save_error = True
                  logger.error(f"No se encontró el usuario {user_id} para añadir el ejercicio resuelto (update_one matched_count=0).")
             elif update_result.modified_count == 0:
                  # Esto puede pasar si el documento ya estaba en el array por alguna razón
                  logger.warning(f"No se modificó el usuario {user_id} al añadir ejercicio (modified_count=0).")
             else:
                  logger.info(f"Ejercicio resuelto añadido correctamente al historial del usuario {user_id}")
        else:
             # Si devolvió algo inesperado
             save_error = True
             logger.error(f"Valor de retorno inesperado de add_solved_exercise para user {user_id}: {type(update_result)}")


    except Exception as e:
        # Capturar errores durante la operación de guardado
        logger.error(f"Error al intentar guardar el ejercicio resuelto para user {user_id} ({problem_id_obj}): {e}", exc_info=True)
        save_error = True
        # No lanzamos excepción aquí para que el frontend reciba el feedback del LLM aunque no se haya guardado.
        # Puedes decidir lanzar una excepción si el guardado es crítico.


    logger.info(f"Evaluación final para {user_email} (problema {problem_id_obj}): Calificación={llm_grade} (Guardado: {'No' if save_error else 'Sí'})")

    # 6. Devolver el feedback al frontend
    # Retornar FeedbackResponse(analysis=..., grade=...)
    return FeedbackResponse(analysis=llm_analysis, grade=llm_grade)

# Asegúrate de que tu modelo FeedbackResponse esté definido en models/logic.py
# Ejemplo:
# from pydantic import BaseModel
# class FeedbackResponse(BaseModel):
#     analysis: str
#     grade: int # O float si tu LLM devuelve float