from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) # para agregar la carpeta padre al path y poder importar las keys
from keys import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
from neo4j_client import Neo4jClient

# Hash de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Para protección de rutas
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

neo4j_client = Neo4jClient()

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Obtiene el usuario actual a partir del token JWT
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    with neo4j_client.get_session() as session:
        result = session.run(
            """
            MATCH (u:User {email: $email})
            RETURN u.email as email, u.username as username
            """,
            email=email
        )
        user = result.single()
        
        if user is None:
            raise credentials_exception
            
        return {"email": user["email"], "username": user["username"]}


