from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import boto3
from keys import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION

router = APIRouter()

# Configuración de AWS Polly
polly_client = boto3.client(
    'polly',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

class TextToSpeechRequest(BaseModel):
    text: str

class ProcessTextRequest(BaseModel):
    userInput: str
    context: Optional[str] = "login_accessibility"

@router.post("/tts/synthesize")
async def synthesize_speech(request: TextToSpeechRequest):
    try:
        response = polly_client.synthesize_speech(
            Text=request.text,
            OutputFormat='mp3',
            VoiceId='Mia',  # Voz en Español México (Neural)
            Engine='neural',  # Asegúrate de usar la voz neural
        )

        return StreamingResponse(
            response['AudioStream'].iter_chunks(),
            media_type="audio/mpeg"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai/process")
async def process_text(request: ProcessTextRequest):
    try:
        # Por ahora, devolvemos una respuesta simple
        return {"response": "Entiendo que quieres " + request.userInput}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 