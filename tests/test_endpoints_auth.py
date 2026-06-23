"""
Tests de endpoints de autenticación:
  POST /auth/register
  POST /auth/login
  GET  /auth/me
  PATCH /auth/me
  PUT  /auth/me/home
"""

from unittest.mock import patch
from tests.conftest import make_user


# ── POST /auth/register ───────────────────────────────────────────────────────

class TestRegister:
    def test_registro_exitoso(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None  # email no existe

        resp = client.post("/auth/register", json={
            "email": "nuevo@test.com",
            "password": "password123",
            "name": "Ana",
            "last_name": "García",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "nuevo@test.com"
        assert data["role"] == "user"

    def test_email_duplicado_retorna_400(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = make_user()

        resp = client.post("/auth/register", json={
            "email": "existe@test.com",
            "password": "password123",
        })
        assert resp.status_code == 400
        assert "ya está registrado" in resp.json()["detail"]

    def test_email_invalido_retorna_422(self, client, mock_db):
        resp = client.post("/auth/register", json={
            "email": "no-es-un-email",
            "password": "password123",
        })
        assert resp.status_code == 422


# ── POST /auth/login ──────────────────────────────────────────────────────────

class TestLogin:
    def _form(self, username="user@test.com", password="correct"):
        return {"username": username, "password": password}

    @patch("app.api.auth.verify_password", return_value=True)
    @patch("app.api.auth.create_access_token", return_value="fake-jwt-token")
    def test_login_exitoso_retorna_token(self, mock_token, mock_verify, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = make_user()

        resp = client.post("/auth/login", data=self._form())
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "fake-jwt-token"
        assert data["token_type"] == "bearer"

    @patch("app.api.auth.verify_password", return_value=False)
    def test_contrasena_incorrecta_retorna_401(self, mock_verify, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = make_user()

        resp = client.post("/auth/login", data=self._form())
        assert resp.status_code == 401

    def test_usuario_no_existe_retorna_401(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None

        resp = client.post("/auth/login", data=self._form())
        assert resp.status_code == 401

    @patch("app.api.auth.verify_password", return_value=True)
    def test_cuenta_bloqueada_retorna_403(self, mock_verify, client, mock_db):
        blocked_user = make_user(is_active=False)
        mock_db.query.return_value.filter.return_value.first.return_value = blocked_user

        resp = client.post("/auth/login", data=self._form())
        assert resp.status_code == 403
        assert "bloqueada" in resp.json()["detail"]


# ── GET /auth/me ──────────────────────────────────────────────────────────────

class TestGetMe:
    def test_retorna_perfil_del_usuario_autenticado(self, client, mock_user):
        resp = client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == mock_user.email


# ── PATCH /auth/me ────────────────────────────────────────────────────────────

class TestUpdateProfile:
    def test_actualiza_nombre(self, client, mock_user, mock_db):
        resp = client.patch("/auth/me", json={"name": "Nuevo Nombre"})
        assert resp.status_code == 200
        assert mock_user.name == "Nuevo Nombre"

    def test_actualiza_solo_campos_enviados(self, client, mock_user, mock_db):
        original_last_name = mock_user.last_name
        client.patch("/auth/me", json={"name": "Solo Nombre"})
        assert mock_user.last_name == original_last_name


# ── PUT /auth/me/home ─────────────────────────────────────────────────────────

class TestUpdateHome:
    def test_actualiza_ubicacion_en_lima(self, client, mock_user, mock_db):
        resp = client.put("/auth/me/home", json={
            "home_lat": -12.046,
            "home_lon": -77.042,
            "home_address": "Av. Larco 123",
        })
        assert resp.status_code == 200
        assert mock_user.home_lat == -12.046

    def test_coordenadas_fuera_de_lima_retorna_400(self, client, mock_db):
        resp = client.put("/auth/me/home", json={
            "home_lat": -16.0,  # Arequipa, fuera del bbox de Lima
            "home_lon": -71.5,
            "home_address": "Dirección fuera de Lima",
        })
        assert resp.status_code == 400
        assert "Lima" in resp.json()["detail"]
