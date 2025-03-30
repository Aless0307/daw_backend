from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
import numpy as np
from azure_storage import upload_voice_recording
from voice_processing import extract_voice_embedding

load_dotenv()

router = APIRouter()

# Configuración de seguridad
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Configuración de Neo4j
uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")
driver = GraphDatabase.driver(uri, auth=(user, password))

# Configuración de JWT
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/register")
async def register(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    voice: Optional[UploadFile] = File(None)
):
    print(f"Recibiendo solicitud de registro:")
    print(f"Username: {username}")
    print(f"Email: {email}")
    print(f"Voice file received: {voice is not None}")

    # Verificar si el usuario ya existe
    with driver.session() as session:
        result = session.run(
            "MATCH (u:User) WHERE u.email = $email OR u.username = $username RETURN u",
            email=email,
            username=username
        )
        if result.single():
            raise HTTPException(
                status_code=400,
                detail="El email o nombre de usuario ya está registrado"
            )

    # Procesar la grabación de voz si se proporciona
    voice_url = None
    voice_embedding = None
    if voice:
        try:
            print("Procesando archivo de voz...")
            # Guardar el archivo temporalmente
            temp_path = f"temp_{voice.filename}"
            with open(temp_path, "wb") as buffer:
                content = await voice.read()
                buffer.write(content)
            print(f"Archivo temporal guardado en: {temp_path}")

            # Extraer el embedding de voz
            voice_embedding = extract_voice_embedding(temp_path)
            print("Embedding de voz extraído correctamente")
            
            # Subir el archivo a Azure
            voice_url = upload_voice_recording(content, None)
            print(f"Archivo subido a Azure. URL: {voice_url}")
            
            # Eliminar el archivo temporal
            os.remove(temp_path)
            print("Archivo temporal eliminado")
            
        except Exception as e:
            print(f"Error al procesar la grabación de voz: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al procesar la grabación de voz: {str(e)}"
            )

    try:
        # Crear el usuario en Neo4j
        with driver.session() as session:
            result = session.run(
                """
                CREATE (u:User {
                    username: $username,
                    email: $email,
                    password: $password,
                    voice_url: $voice_url,
                    voice_embedding: $voice_embedding
                })
                RETURN elementId(u) as id, u
                """,
                username=username,
                email=email,
                password=get_password_hash(password),
                voice_url=voice_url,
                voice_embedding=voice_embedding.tolist() if voice_embedding is not None else None
            )
            user_data = result.single()
            user_id = user_data["id"]
            print(f"Usuario creado exitosamente con ID: {user_id}")

        return {
            "message": "Usuario registrado exitosamente",
            "user_id": user_id
        }
    except Exception as e:
        print(f"Error al crear usuario en Neo4j: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al crear usuario en la base de datos: {str(e)}"
        )

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    with driver.session() as session:
        result = session.run(
            """
            MATCH (u:User) 
            WHERE u.email = $email 
            RETURN elementId(u) as id, u
            """,
            email=form_data.username
        )
        user = result.single()
        
        if not user or not verify_password(form_data.password, user["u"]["password"]):
            raise HTTPException(
                status_code=401,
                detail="Credenciales incorrectas"
            )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["u"]["email"], "id": user["id"]},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user["u"]["username"],
        "email": user["u"]["email"],
        "user_id": user["id"]
    }

@router.post("/login-voice")
async def login_voice(voice: UploadFile = File(...)):
    try:
        # Guardar el archivo temporalmente
        temp_path = f"temp_{voice.filename}"
        with open(temp_path, "wb") as buffer:
            content = await voice.read()
            buffer.write(content)

        # Extraer el embedding de voz
        voice_embedding = extract_voice_embedding(temp_path)
        
        # Eliminar el archivo temporal
        os.remove(temp_path)
        
        # Buscar usuario con embedding similar
        with driver.session() as session:
            result = session.run(
                """
                MATCH (u:User)
                WHERE u.voice_embedding IS NOT NULL
                RETURN elementId(u) as id, u
                """
            )
            
            best_match = None
            best_similarity = 0
            
            for record in result:
                stored_embedding = np.array(record["u"]["voice_embedding"])
                similarity = np.dot(voice_embedding, stored_embedding) / (
                    np.linalg.norm(voice_embedding) * np.linalg.norm(stored_embedding)
                )
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = record
            
            if best_match and best_similarity >= 0.7:  # Umbral de similitud
                access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
                access_token = create_access_token(
                    data={"sub": best_match["u"]["email"], "id": best_match["id"]},
                    expires_delta=access_token_expires
                )
                
                return {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "username": best_match["u"]["username"],
                    "email": best_match["u"]["email"],
                    "user_id": best_match["id"]
                }
            else:
                raise HTTPException(
                    status_code=401,
                    detail="No se encontró una coincidencia de voz válida"
                )
                
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar la grabación de voz: {str(e)}"
        ) 