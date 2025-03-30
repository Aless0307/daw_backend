from fastapi import APIRouter, HTTPException
from models.user import UserCreate
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) # para agregar la carpeta padre al path y poder importar las keys
from Database.neo4j_conn import get_neo4j_session
from auth_utils import hash_password
router = APIRouter()


# ██████╗░███████╗░██████╗░██╗░██████╗████████╗██████╗░░█████╗░
# ██╔══██╗██╔════╝██╔════╝░██║██╔════╝╚══██╔══╝██╔══██╗██╔══██╗
# ██████╔╝█████╗░░██║░░██╗░██║╚█████╗░░░░██║░░░██████╔╝██║░░██║
# ██╔══██╗██╔══╝░░██║░░╚██╗██║░╚═══██╗░░░██║░░░██╔══██╗██║░░██║
# ██║░░██║███████╗╚██████╔╝██║██████╔╝░░░██║░░░██║░░██║╚█████╔╝
# ╚═╝░░╚═╝╚══════╝░╚═════╝░╚═╝╚═════╝░░░░╚═╝░░░╚═╝░░╚═╝░╚════╝░

# La ruta para registrar un usuario
@router.post("/register")
def register(user: UserCreate):
    session = get_neo4j_session()

    # Verificar si ya existe
    existing = session.run(
        "MATCH (u:User {email: $email}) RETURN u",
        email=user.email
    ).single()
    
    if existing: # Si el usuario ya existe, se lanza una excepción
        raise HTTPException(status_code=400, detail="El usuario ya existe")

    # Se crea el usuario con la contraseña encriptada
    session.run(
        "CREATE (u:User {username: $username, email: $email, password: $password})",
        username=user.username,
        email=user.email,
        password=hash_password(user.password)
    )

    return {"message": "✅ Usuario registrado correctamente"}



# ██╗░░░░░░█████╗░░██████╗░██╗███╗░░██╗
# ██║░░░░░██╔══██╗██╔════╝░██║████╗░██║
# ██║░░░░░██║░░██║██║░░██╗░██║██╔██╗██║
# ██║░░░░░██║░░██║██║░░╚██╗██║██║╚████║
# ███████╗╚█████╔╝╚██████╔╝██║██║░╚███║
# ╚══════╝░╚════╝░░╚═════╝░╚═╝╚═╝░░╚══╝

from fastapi import status
from pydantic import BaseModel
from auth.auth_utils import verify_password, create_access_token

# Esta clase define el modelo de datos para el login
class LoginData(BaseModel):
    email: str
    password: str

# Esta ruta maneja el login de un usuario
@router.post("/login")
def login(data: LoginData):
    session = get_neo4j_session()

    user_node = session.run( # Se busca el usuario en la base de datos
        "MATCH (u:User {email: $email}) RETURN u LIMIT 1",
        email=data.email
    ).single()

    if not user_node: # Si el usuario no existe, se lanza una excepción
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    user = user_node["u"] # Se obtiene el usuario
    if not verify_password(data.password, user["password"]): # Si la contraseña no es correcta, se lanza una excepción
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    token = create_access_token({"sub": user["email"]}) # Se crea el token de acceso
    return { # Se devuelve el token de acceso que contiene el nombre de usuario y el correo electrónico y se envia al frontend
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "email": user["email"]
    }
