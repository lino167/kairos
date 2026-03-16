import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai

async def test_gemini():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY não encontrada no .env")
        return

    genai.configure(api_key=api_key)
    
    print("[*] Listando modelos disponiveis...")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"  - {m.name}")
    except Exception as e:
        print(f"❌ Erro ao listar modelos: {e}")

    models = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-pro']
    
    for model_name in models:
        try:
            print(f"\n[*] Testando modelo: {model_name}...")
            # Tenta sem o prefixo models/ se o SDK ja adicionar
            model = genai.GenerativeModel(model_name)
            response = model.generate_content("Responda apenas 'OK' se estiver funcionando.")
            
            try:
                print(f"OK Sucesso com {model_name}: {response.text}")
            except Exception as inner_e:
                print(f"Erro ao acessar .text em {model_name}: {inner_e}")
                if hasattr(response, 'prompt_feedback'):
                    print(f"   Feedback: {response.prompt_feedback}")
        except Exception as e:
            print(f"Falha com {model_name}: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
