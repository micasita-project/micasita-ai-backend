"""
Tests directos de las dependencias de autenticación en app/core/security.py.

`get_current_user` y `get_current_user_optional` se llaman como funciones
planas (no vía FastAPI DI) para poder probar el chequeo de `is_active` sin
que `client`/`mock_user` (que sobreescriben estas dependencias) lo tapen.
"""

import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

from app.core.security import get_current_user, get_current_user_optional, create_access_token
from tests.conftest import make_user


def _db_returning(user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


class TestGetCurrentUser:
    def test_usuario_activo_se_autentica(self):
        user = make_user(is_active=True)
        token = create_access_token({"sub": user.email})
        result = get_current_user(token=token, db=_db_returning(user))
        assert result is user

    def test_usuario_bloqueado_lanza_403(self):
        # Un token emitido antes del bloqueo no debe seguir sirviendo para
        # autenticar en endpoints protegidos.
        user = make_user(is_active=False)
        token = create_access_token({"sub": user.email})
        with pytest.raises(HTTPException) as exc:
            get_current_user(token=token, db=_db_returning(user))
        assert exc.value.status_code == 403

    def test_usuario_inexistente_lanza_401(self):
        token = create_access_token({"sub": "fantasma@test.com"})
        with pytest.raises(HTTPException) as exc:
            get_current_user(token=token, db=_db_returning(None))
        assert exc.value.status_code == 401

    def test_sin_token_lanza_401(self):
        with pytest.raises(HTTPException) as exc:
            get_current_user(token=None, db=_db_returning(None))
        assert exc.value.status_code == 401


class TestGetCurrentUserOptional:
    def test_usuario_activo_se_resuelve(self):
        user = make_user(is_active=True)
        token = create_access_token({"sub": user.email})
        result = get_current_user_optional(token=token, db=_db_returning(user))
        assert result is user

    def test_usuario_bloqueado_se_resuelve_a_none(self):
        # A diferencia de get_current_user, esta variante nunca lanza — una
        # cuenta bloqueada debe tratarse como anónima, no reventar la petición.
        user = make_user(is_active=False)
        token = create_access_token({"sub": user.email})
        result = get_current_user_optional(token=token, db=_db_returning(user))
        assert result is None

    def test_sin_token_se_resuelve_a_none(self):
        assert get_current_user_optional(token=None, db=_db_returning(None)) is None
