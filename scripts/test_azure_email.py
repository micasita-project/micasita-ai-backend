import os
import sys

# Agregamos la ruta principal al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.email import email_service
from app.core.config import settings

def test_send():
    print(f"Probando envío de correo desde: {settings.AZURE_EMAIL_SENDER}")
    
    # Reemplaza con un correo tuyo para probar
    test_receiver = "jose.calderon.h@uni.pe" # Ejemplo, el usuario debería cambiarlo
    
    subject = "Prueba de MiCasita AI"
    html_content = """
    <html>
        <body>
            <h1 style="color: #4A90E2;">¡Hola desde MiCasita!</h1>
            <p>Esta es una prueba del servicio de <strong>Azure Communication Services</strong>.</p>
            <p>Si recibes esto, la integración backend está lista. 🚀</p>
        </body>
    </html>
    """
    
    success = email_service.send_email(test_receiver, subject, html_content)
    
    if success:
        print("¡Éxito! Revisa tu bandeja de entrada (o spam).")
    else:
        print("Falló el envío. Revisa los logs y asegúrate de que el AZURE_EMAIL_SENDER sea correcto.")

if __name__ == "__main__":
    test_send()
