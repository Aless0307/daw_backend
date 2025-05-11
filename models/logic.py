# models/logic.py
from pydantic import BaseModel, Field # Importa Field
from typing import Dict, Optional, List, Union # Importa List y Union
from bson import ObjectId # Importa ObjectId

# --- Modelos Existentes ---
# Modelo para el progreso en una dificultad específica
class DifficultyProgress(BaseModel):
    solved_count: int = 0
    average_grade: float = 0.0

# Modelo principal para la respuesta del progreso general del usuario
class UserProgressResponse(BaseModel):
    total_solved: int = 0
    progress_by_difficulty: Dict[str, DifficultyProgress] = {}
    overall_average_grade: float = 0.0
    message: str = "Progreso cargado exitosamente"

    # Para Pydantic v2+ (si aplica)
    # from pydantic import ConfigDict
    # model_config = ConfigDict(populate_by_name=True)


# --- Nuevos Modelos para la Respuesta del Problema ---

# Modelo para un problema individual
class ProblemResponse(BaseModel):
    # Mapea el campo '_id' de MongoDB (ObjectId) a 'id' en el modelo y JSON
    id: str = Field(alias="_id")
    text: str
    difficulty: str
    topics: List[str] = [] # Incluimos topics ya que los insertamos

    class Config:
        # Permite mapear por alias ('_id' a 'id')
        populate_by_name = True
        # Configuración para serializar ObjectId a string (para Pydantic v1 y v2)
        json_encoders = {ObjectId: str}

        # Para Pydantic V2+, también puedes añadir ejemplos (Opcional para docs)
        # json_schema_extra = {
        #     "example": {
        #         "id": "60d5ec49b8f9c40e6c1a0d9e",
        #         "text": "¿Cómo invertirías una cadena de texto?",
        #         "difficulty": "basico",
        #         "topics": ["cadenas", "inversion"]
        #     }
        # }

# Modelo para la respuesta cuando no se encuentran problemas sin resolver
class NoProblemResponse(BaseModel):
    message: str = "No se encontraron problemas sin resolver para la dificultad especificada."
    # Puedes añadir campos opcionales si quieres devolver más contexto (ej. requested_difficulty: Optional[str] = None)

class FeedbackResponse(BaseModel):
    analysis: str
    # --- RANGO 0-10 ---
    grade: Union[int, float] = Field(..., ge=0, le=10) # Permitir hasta 10
    # --- FIN AJUSTE ---

    class Config:
         orm_mode = True # O from_attributes = True en Pydantic v2
         schema_extra = { # O model_config = {"json_schema_extra": ...} en Pydantic v2
             "example": {
                 "analysis": "Buen intento, considera los casos borde.",
                 "grade": 7 # Ejemplo con nota 0-10
             }
         }
         
# --- Nuevo Modelo para el cuerpo de la solicitud TTS ---
class TTSTextRequest(BaseModel):
    text: str # Esperamos un campo 'text' que sea una cadena
