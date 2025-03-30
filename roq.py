import httpx
import asyncio
from keys import GROQ_API_KEY

async def preguntar_a_groq(pregunta):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama3-70b-8192",  # Modelo actualizado que está disponible
        "messages": [
            {"role": "user", "content": pregunta}
        ],
        "temperature": 0.7
    }
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload
        )
        
        # Intenta extraer la respuesta
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except KeyError:
            return "❌ Error: No se recibió una respuesta válida del modelo."

if __name__ == "__main__":
    pregunta = input("💬 Escribe tu pregunta: ")
    respuesta = asyncio.run(preguntar_a_groq(pregunta))
    print(f"\n🧠 Respuesta de Groq:\n{respuesta}")