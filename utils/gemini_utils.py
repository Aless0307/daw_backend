# utils/gemini_utils.py (o donde esté definida la función)

import google.generativeai as genai
import os
import logging
import json # Necesario para parsear
import re   # Necesario para limpiar la respuesta

# Configurar logging para este módulo
logger = logging.getLogger(__name__)

# Configurar API Key (MEJOR desde variables de entorno)
GEMINI_API_KEY = "AIzaSyClAldN4Lvq3HjK1MgogyFdMzitzAqAkXM" 
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY no encontrada en variables de entorno.")
    # Considera añadir una clave por defecto aquí SOLO para desarrollo local
    # y con mucho cuidado de no subirla a repositorios públicos.
    # GEMINI_API_KEY = "TU_CLAVE_GEMINI_AQUI"

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        logger.info("Cliente de Google Generative AI configurado.")
    except Exception as e:
        logger.error(f"Error al configurar Google Generative AI: {e}")
else:
     logger.error("No se pudo configurar Google Generative AI: API Key ausente.")


# Configuración del modelo (Asegúrate de que estas variables estén definidas o pásalas como argumento)
# Ejemplo:
generation_config = {
  "temperature": 0.6, # Ajustado para ser un poco más determinista
  "top_p": 1,
  "top_k": 1,
  "max_output_tokens": 1024, # Puedes ajustar esto
}
safety_settings = [
  {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
  {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
  {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
  {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

# --- FUNCIÓN CORREGIDA ---
async def get_gemini_feedback(problem_text: str, user_answer: str) -> dict | None:
    """
    Llama a la API de Gemini para obtener análisis y calificación (0-10).
    Limpia la respuesta para extraer JSON antes de parsear.

    Returns:
        Un diccionario como {"analysis": "...", "grade": X} o un diccionario
        de fallback con grade=0 si la llamada o el parseo fallan.
        Devuelve None solo si la API Key no está configurada.
    """
    if not GEMINI_API_KEY:
        logger.error("Intento de llamar a Gemini sin API Key configurada.")
        # Devolver un diccionario de error consistente es mejor que None aquí
        return {"analysis": "Error interno: API Key de Gemini no configurada.", "grade": 0}

    try:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash", # Asegúrate que este sea el modelo correcto
            generation_config=generation_config,
            safety_settings=safety_settings
        )

        # --- PROMPT REFINADO ---
        prompt = f"""
        Eres un asistente experto y amable que evalúa respuestas a problemas de lógica de programación para estudiantes.
        IMPORTANTE: La respuesta del usuario viene de una transcripción de voz, por lo que puede contener pequeños errores (ej. 'ford' en vez de 'for', 'smart.h' en vez de 'math.h', etc.). Sé un poco tolerante con estos errores menores si la lógica subyacente es comprensible. Enfócate en evaluar el *proceso lógico* descrito.

        Evalúa la siguiente respuesta de un usuario al problema dado. Proporciona:
        1. Un análisis constructivo y conciso sobre la LÓGICA de la respuesta. Indica si el enfoque es correcto, si es eficiente, si considera casos borde (si aplica), y ofrece sugerencias claras de mejora. Evita juzgar errores menores de sintaxis o nombres si la idea es clara. Si el usuario menciona una función o concepto clave (como 'len' o 'bucle'), reconócelo positivamente si es apropiado para el problema.
        2. Una calificación numérica ENTERA del 0 al 10. Escala: 0=Vacío/Sin sentido, 1-3=Incorrecto/Muy incompleto, 4-6=Idea básica correcta pero con errores lógicos o muy incompleta, 7-8=Correcto pero mejorable (claridad, eficiencia), 9=Muy bien, casi perfecto, 10=Perfecto, claro, conciso y eficiente.
        3. Trata de darle sentido y construir lo que el usuario intentó decir, incluso si no es perfecto. No te limites a señalar errores, sino a ayudar al usuario a mejorar su respuesta. Pero en caso de errores graves, sé claro y directo. Recuerda que el usuario es un estudiante y no un experto. Además de que el usuario está aprendiendo y habla mientras piensa y desarrolla su respuesta. Entonces puede haber trabas, repeticiones, palabras sin sentido, malas transcripciones de la API de speech-to-text, etc. No te limites a señalar errores, sino a ayudar al usuario a mejorar su respuesta, etc. Enfócate en evaluar el proceso lógico descrito.
        Problema:
        \"\"\"
        {problem_text}
        \"\"\"

        Respuesta del Usuario (transcrita de voz):
        \"\"\"
        {user_answer}
        \"\"\"

        RESPUESTA OBLIGATORIA EN FORMATO JSON VÁLIDO (SOLO EL JSON, SIN NADA MÁS ANTES O DESPUÉS, SIN MARKDOWN ```json ... ```):
        {{"analysis": "string con tu análisis aquí", "grade": integer de 0 a 10 aquí}}
        """
        # --- FIN PROMPT ---

        logger.info("Generando contenido con Gemini...")

        # --- IMPORTANTE: LLAMADA A GEMINI ---
        # La función model.generate_content ES SÍNCRONA en la librería actual.
        # Por lo tanto, DEBE ser llamada usando asyncio.to_thread DESDE EL ROUTER (endpoint).
        # La firma de ESTA función (get_gemini_feedback) puede ser 'def' normal, no necesita 'async def'.
        # Si la dejas como 'async def', la llamada en el router DEBE seguir siendo
        # await asyncio.to_thread(get_gemini_feedback, ...) porque la operación interna bloquea.
        # Vamos a mantenerla async por ahora, pero recuerda cómo llamarla desde el router.
        response = model.generate_content(prompt)
        # --- FIN LLAMADA A GEMINI ---


        raw_text = response.text.strip()
        logger.debug(f"Respuesta cruda de Gemini recibida: {raw_text}")

        # --- INICIO: LIMPIEZA Y PARSEO JSON ---
        json_str = None
        # Intentar extraer JSON dentro de ```json ... ``` o solo ``` ... ```
        match = re.search(r"```(?:json)?\s*({.*?})\s*```", raw_text, re.DOTALL | re.IGNORECASE)
        if match:
            json_str = match.group(1) # Captura el contenido entre llaves {}
            logger.info("JSON extraído de bloque Markdown.")
        else:
            # Si no hay bloques markdown, intentar usar el texto crudo
            json_str = raw_text
            logger.info("No se encontraron bloques Markdown, intentando parsear texto crudo como JSON.")

        feedback = None
        if json_str:
            try:
                # Intentar parsear la cadena extraída o cruda
                feedback_data = json.loads(json_str)

                # Validar estructura básica y tipos
                if isinstance(feedback_data, dict) and \
                   "analysis" in feedback_data and \
                   "grade" in feedback_data and \
                   isinstance(feedback_data["analysis"], str) and \
                   isinstance(feedback_data["grade"], (int, float)):

                    # Validar y asegurar rango de nota 0-10
                    try:
                         grade_val = float(feedback_data["grade"]) # Convertir a float por si acaso
                         final_grade = round(max(0.0, min(10.0, grade_val))) # Redondear a entero 0-10
                    except (ValueError, TypeError):
                         logger.error(f"Valor de 'grade' no es numérico en JSON: {feedback_data.get('grade')}. Usando 0.")
                         final_grade = 0

                    feedback = {
                        "analysis": feedback_data["analysis"].strip(),
                        "grade": final_grade
                    }
                    logger.info(f"Feedback parseado y validado de Gemini: Calificación={feedback['grade']}")

                else:
                    logger.error(f"JSON parseado no tiene la estructura esperada (analysis, grade): {feedback_data}")
                    feedback = {"analysis": f"Respuesta de IA (estructura JSON inesperada): {raw_text}", "grade": 0}

            except json.JSONDecodeError:
                logger.error(f"Respuesta de Gemini no es JSON válido (incluso después de limpiar): {json_str}")
                feedback = {"analysis": f"Respuesta de IA (no JSON / error parseo): {raw_text}", "grade": 0}
        else:
             logger.error("No se pudo extraer contenido JSON de la respuesta de Gemini.")
             feedback = {"analysis": f"Respuesta de IA (sin JSON extraíble): {raw_text}", "grade": 0}

        return feedback
        # --- FIN LIMPIEZA Y PARSEO ---

    except Exception as e:
        # Captura cualquier otro error durante la configuración o llamada a Gemini
        logger.error(f"Error general al llamar/configurar Gemini: {e}", exc_info=True)
        # Devolver un feedback de error genérico en lugar de None ayuda al endpoint
        return {"analysis": f"Error al contactar al asistente de IA: {str(e)}", "grade": 0}