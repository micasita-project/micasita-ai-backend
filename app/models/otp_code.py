from sqlalchemy import Column, Integer, String, DateTime, Index
from app.core.database import Base


class OtpCode(Base):
    """
    Almacén persistente de códigos OTP.

    Reemplaza el antiguo almacenamiento en memoria para que los códigos
    sobrevivan reinicios del servidor y funcionen con múltiples instancias.
    Cada (email, purpose) tiene a lo sumo un código vigente.
    """
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, index=True)
    purpose = Column(String, nullable=False)  # "password_reset" | "email_verify"
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_otp_codes_email_purpose", "email", "purpose"),
    )
