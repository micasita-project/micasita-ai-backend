import requests
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

SENDGRID_ENDPOINT = "https://api.sendgrid.com/v3/mail/send"


class EmailService:
    def __init__(self):
        self.api_key = settings.SENDGRID_API_KEY
        self.sender_email = settings.SENDGRID_EMAIL_SENDER
        self.sender_name = "MiCasita"

    def send_email(self, to_address: str, subject: str, html_content: str) -> bool:
        try:
            response = requests.post(
                SENDGRID_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": to_address}]}],
                    "from": {"email": self.sender_email, "name": self.sender_name},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": html_content}],
                },
                timeout=10,
            )
            if not response.ok:
                logger.error(f"SendGrid error {response.status_code}: {response.text}")
                return False
            logger.info(f"Correo enviado a {to_address}")
            return True
        except Exception as e:
            logger.error(f"Error enviando correo a {to_address}: {e}")
            return False


email_service = EmailService()
