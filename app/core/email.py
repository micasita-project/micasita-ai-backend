import resend
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

resend.api_key = settings.RESEND_API_KEY


class EmailService:
    def __init__(self):
        self.sender_address = settings.RESEND_EMAIL_SENDER

    def send_email(self, to_address: str, subject: str, html_content: str):
        try:
            resend.Emails.send({
                "from": self.sender_address,
                "to": [to_address],
                "subject": subject,
                "html": html_content,
            })
            logger.info(f"Correo enviado exitosamente a {to_address}")
            return True
        except Exception as e:
            logger.error(f"Error enviando correo a {to_address}: {e}")
            return False


email_service = EmailService()
