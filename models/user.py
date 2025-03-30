from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel): # Esta clase es para la creación de un usuario, en este caso se validan los datos recibidos
    username: str
    email: EmailStr
    password: str
