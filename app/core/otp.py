import secrets
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.models.otp_code import OtpCode


class OTPStore:
    """
    Almacén de OTP respaldado por PostgreSQL.

    Cada instancia maneja un propósito distinto ("password_reset" /
    "email_verify"). Los códigos sobreviven reinicios del servidor y son
    consistentes entre múltiples instancias (a diferencia del almacén en
    memoria anterior). Gestiona su propia sesión de BD porque algunos
    `generate()` se ejecutan dentro de BackgroundTasks (fuera del request).
    """

    def __init__(self, purpose: str, expiry_seconds: int):
        self.purpose = purpose
        self.expiry = expiry_seconds

    def generate(self, key: str) -> str:
        code = str(secrets.randbelow(1_000_000)).zfill(6)
        expires_at = datetime.utcnow() + timedelta(seconds=self.expiry)
        db = SessionLocal()
        try:
            # Sustituye cualquier OTP previo del mismo propósito para este email
            db.query(OtpCode).filter(
                OtpCode.email == key,
                OtpCode.purpose == self.purpose,
            ).delete(synchronize_session=False)
            db.add(OtpCode(
                email=key,
                purpose=self.purpose,
                code=code,
                expires_at=expires_at,
            ))
            db.commit()
        finally:
            db.close()
        return code

    def verify(self, key: str, code: str) -> bool:
        db = SessionLocal()
        try:
            entry = db.query(OtpCode).filter(
                OtpCode.email == key,
                OtpCode.purpose == self.purpose,
            ).first()
            if not entry:
                return False
            if datetime.utcnow() > entry.expires_at:
                db.delete(entry)
                db.commit()
                return False
            if entry.code != code:
                return False
            db.delete(entry)  # un solo uso
            db.commit()
            return True
        finally:
            db.close()

    def has_pending(self, key: str) -> bool:
        db = SessionLocal()
        try:
            entry = db.query(OtpCode).filter(
                OtpCode.email == key,
                OtpCode.purpose == self.purpose,
            ).first()
            if not entry:
                return False
            if datetime.utcnow() > entry.expires_at:
                db.delete(entry)
                db.commit()
                return False
            return True
        finally:
            db.close()


# 15 min para reset de contraseña, 24 h para verificación de correo
password_reset_store = OTPStore(purpose="password_reset", expiry_seconds=900)
email_verify_store = OTPStore(purpose="email_verify", expiry_seconds=86400)
