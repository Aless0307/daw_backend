# daw_backend/main.py
from fastapi import FastAPI
from auth import login
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.include_router(login.router)

# Para permitir llamadas desde tu frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en producción usa ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

