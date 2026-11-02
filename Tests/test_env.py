# tests/test_env.py

from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("LABELBOX_API_KEY")

if api_key:
    print("✅ API_KEY cargada correctamente")
else:
    print("❌ API_KEY no encontrada")