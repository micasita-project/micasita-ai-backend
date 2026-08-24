"""
Tests para app/core/otp.py: expiración, consumo de un solo uso y límite de
intentos del código OTP.

OTPStore gestiona su propia sesión de BD en cada llamada (no admite mock de
sesión), así que se ejercita contra la BD de test real (SQLite). Solo se crea
la tabla otp_codes — crear todo Base.metadata fallaría en SQLite por la
columna geography (PostGIS) de Property.
"""

import pytest
from datetime import datetime, timedelta

from app.core.database import engine, SessionLocal
from app.models.otp_code import OtpCode
from app.core.otp import OTPStore

OtpCode.__table__.create(bind=engine, checkfirst=True)


@pytest.fixture(autouse=True)
def limpiar_otp_codes():
    db = SessionLocal()
    db.query(OtpCode).delete()
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.query(OtpCode).delete()
    db.commit()
    db.close()


class TestOTPStoreVerify:
    def test_codigo_correcto_retorna_true_y_se_consume(self):
        store = OTPStore(purpose="test_purpose", expiry_seconds=900)
        code = store.generate("user@test.com")
        assert store.verify("user@test.com", code) is True
        # Un solo uso: la segunda vez ya no existe
        assert store.verify("user@test.com", code) is False

    def test_codigo_incorrecto_retorna_false(self):
        store = OTPStore(purpose="test_purpose", expiry_seconds=900)
        store.generate("user@test.com")
        assert store.verify("user@test.com", "000000") is False

    def test_codigo_expirado_retorna_false(self):
        store = OTPStore(purpose="test_purpose", expiry_seconds=900)
        code = store.generate("user@test.com")
        db = SessionLocal()
        entry = db.query(OtpCode).filter(OtpCode.email == "user@test.com").first()
        entry.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        db.close()
        assert store.verify("user@test.com", code) is False

    def test_agota_intentos_e_invalida_el_codigo(self):
        store = OTPStore(purpose="test_purpose", expiry_seconds=900, max_attempts=3)
        code = store.generate("user@test.com")
        for _ in range(3):
            assert store.verify("user@test.com", "000000") is False
        # El código correcto ya no sirve: se agotaron los intentos
        assert store.verify("user@test.com", code) is False

    def test_intentos_fallidos_no_consumen_el_codigo_antes_de_agotarse(self):
        store = OTPStore(purpose="test_purpose", expiry_seconds=900, max_attempts=5)
        code = store.generate("user@test.com")
        store.verify("user@test.com", "000000")  # 1 fallo
        store.verify("user@test.com", "111111")  # 2 fallos
        # Con intentos de sobra, el código correcto todavía funciona
        assert store.verify("user@test.com", code) is True

    def test_generate_reinicia_intentos_de_un_codigo_previo(self):
        store = OTPStore(purpose="test_purpose", expiry_seconds=900, max_attempts=2)
        store.generate("user@test.com")
        store.verify("user@test.com", "000000")  # 1 fallo
        store.verify("user@test.com", "000000")  # 2 fallos → agota
        new_code = store.generate("user@test.com")  # nuevo código, reinicia intentos
        assert store.verify("user@test.com", new_code) is True
