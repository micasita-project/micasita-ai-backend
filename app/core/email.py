from azure.communication.email import EmailClient
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        try:
            self.client = EmailClient.from_connection_string(settings.AZURE_COMMUNICATION_CONNECTION_STRING)
            self.sender_address = settings.AZURE_EMAIL_SENDER
        except Exception as e:
            logger.error(f"Error inicializando el cliente de Email de Azure: {e}")
            self.client = None

    def send_email(self, to_address: str, subject: str, html_content: str):
        if not self.client:
            logger.error("No se puede enviar correo: Cliente de Azure no inicializado.")
            return False

        message = {
            "content": {
                "subject": subject,
                "html": html_content
            },
            "recipients": {
                "to": [{"address": to_address}]
            },
            "senderAddress": self.sender_address
        }

        try:
            poller = self.client.begin_send(message)
            result = poller.result()
            logger.info(f"Correo enviado exitosamente a {to_address}. MessageId: {result.get('id')}")
            return True
        except Exception as e:
            logger.error(f"Error enviando correo a {to_address}: {e}")
            return False

# Instancia singleton para usar en toda la app
email_service = EmailService()
