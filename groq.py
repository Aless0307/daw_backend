from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
import logging
import requests
from config import GROQ_API_KEY, REQUEST_TIMEOUT
from utils.auth_utils import get_current_user

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('groq.log')
    ]
)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/chat")
async def chat_with_groq(
    message: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Envía un mensaje a la API de GROQ y devuelve la respuesta
    """
    try:
        if not GROQ_API_KEY:
            logger.error("GROQ_API_KEY no configurada")
            return JSONResponse(
                status_code=500,
                content={"detail": "API key de GROQ no configurada"}
            )
        
        # Configurar la llamada a la API
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "messages": [
                {"role": "user", "content": message}
            ],
            "model": "mixtral-8x7b-32768"
        }
        
        # Realizar la llamada
        logger.info(f"Enviando mensaje a GROQ: {message[:50]}...")
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=REQUEST_TIMEOUT
        )
        
        # Verificar la respuesta
        if response.status_code != 200:
            logger.error(f"Error en la respuesta de GROQ: {response.status_code} - {response.text}")
            return JSONResponse(
                status_code=response.status_code,
                content={"detail": "Error al procesar la solicitud con GROQ"}
            )
        
        # Extraer la respuesta
        result = response.json()
        reply = result["choices"][0]["message"]["content"]
        
        logger.info(f"Respuesta recibida de GROQ: {reply[:50]}...")
        return {"reply": reply}
        
    except requests.exceptions.Timeout:
        logger.error("Timeout al llamar a la API de GROQ")
        return JSONResponse(
            status_code=504,
            content={"detail": "Timeout al procesar la solicitud"}
        )
    except Exception as e:
        logger.error(f"Error al llamar a la API de GROQ: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"}
        ) 