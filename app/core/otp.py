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

    `max_attempts` limita la fuerza bruta sobre el código de 6 dígitos: sin
    esto, un atacante tiene toda la ventana de validez (15 min o 24 h) para
    probar el espacio completo de 10⁶ combinaciones sin ninguna fricción.
    """

    def __init__(self, purpose: str, expiry_seconds: int, max_attempts: int = 5):
        self.purpose = purpose
        self.expiry = expiry_seconds
        self.max_attempts = max_attempts

    def generate(self, key: str) -> str:
        code = str(secrets.randbelow(1_000_000)).zfill(6)
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=self.expiry)
        db = SessionLocal()
        try:
            # Limpieza oportunista: borra todos los OTP vencidos (de cualquier
            # email/propósito) para que la tabla no se acumule con el tiempo.
            db.query(OtpCode).filter(OtpCode.expires_at < now).delete(synchronize_session=False)
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
            if entry.attempts >= self.max_attempts:
                # Se agotaron los intentos: se invalida el código para forzar
                # un reenvío en vez de dejarlo abierto indefinidamente.
                db.delete(entry)
                db.commit()
                return False
            if entry.code != code:
                entry.attempts += 1
                db.commit()
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


def purge_expired_otps() -> int:
    """Elimina todos los OTP vencidos. Devuelve cuántas filas se borraron.

    Se ejecuta al arrancar la app (además de la limpieza oportunista en
    cada `generate`), cubriendo el caso en que el servicio estuvo inactivo.
    """
    db = SessionLocal()
    try:
        deleted = db.query(OtpCode).filter(
            OtpCode.expires_at < datetime.utcnow()
        ).delete(synchronize_session=False)
        db.commit()
        return deleted
    finally:
        db.close()


# 15 min para reset de contraseña, 24 h para verificación de correo
password_reset_store = OTPStore(purpose="password_reset", expiry_seconds=900)
email_verify_store = OTPStore(purpose="email_verify", expiry_seconds=86400)
