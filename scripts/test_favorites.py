import os
import sys
import requests

# Agregamos la ruta principal al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://localhost:8000"

def test_favorites():
    # Nota: Este test asume que el servidor está corriendo y tienes un token válido.
    # Como no tengo el token aquí, esto es solo una guía de cómo probarlo con curl o Postman.
    print("--- Guía para probar Favoritos ---")
    print(f"1. Añadir a favoritos: POST {BASE_URL}/properties/1/favorite")
    print(f"2. Listar favoritos: GET {BASE_URL}/properties/favorites")
    print(f"3. Quitar de favoritos: DELETE {BASE_URL}/properties/1/favorite")
    print("\nRECUERDA: Debes enviar el header 'Authorization: Bearer <TU_TOKEN>'")

if __name__ == "__main__":
    test_favorites()
