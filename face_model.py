# daw_backend/face_model.py
import contextlib
import io
from insightface.app import FaceAnalysis

# Silenciar salida
f = io.StringIO()
with contextlib.redirect_stdout(f):
    face_analyzer = FaceAnalysis(providers=['CPUExecutionProvider'])
    face_analyzer.prepare(ctx_id=0, det_size=(640, 640))
print("Modelo de reconocimiento facial cargado exitosamente")