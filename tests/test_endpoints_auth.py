"""
Tests de endpoints de autenticación:
  POST /auth/register
  POST /auth/login
  GET  /auth/me
  PATCH /auth/me
  PUT  /auth/me/home
  POST /auth/me/consent
  DELETE /auth/me
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
            "accepted_terms": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "nuevo@test.com"
        assert data["role"] == "user"

    def test_registro_guarda_fecha_y_version_del_consentimiento(self, client, mock_db):
        from app.core.privacy import PRIVACY_POLICY_VERSION
        mock_db.query.return_value.filter.return_value.first.return_value = None

        client.post("/auth/register", json={
            "email": "nuevo@test.com", "password": "password123", "accepted_terms": True,
        })

        creado = mock_db.add.call_args.args[0]
        assert creado.consent_accepted_at is not None
        assert creado.consent_version == PRIVACY_POLICY_VERSION

    def test_registro_sin_aceptar_la_politica_retorna_400_y_no_crea_cuenta(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None

        resp = client.post("/auth/register", json={
            "email": "nuevo@test.com", "password": "password123", "accepted_terms": False,
        })

        assert resp.status_code == 400
        assert "Política de Privacidad" in resp.json()["detail"]
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_registro_sin_el_campo_de_consentimiento_tambien_se_rechaza(self, client, mock_db):
        resp = client.post("/auth/register", json={"email": "nuevo@test.com", "password": "password123"})

        assert resp.status_code == 400
        mock_db.add.assert_not_called()

    def test_email_duplicado_y_verificado_retorna_400(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = make_user(email_verified=True)

        resp = client.post("/auth/register", json={
            "email": "existe@test.com",
            "password": "password123",
            "accepted_terms": True,
        })
        assert resp.status_code == 400
        assert "ya está registrado" in resp.json()["detail"]

    def test_email_existente_pero_no_verificado_permite_reintentar(self, client, mock_db):
        # Registro previo abandonado (nunca completó el OTP): no debe quedar
        # bloqueado para siempre — se reemplaza con los datos nuevos.
        pendiente = make_user(email="existe@test.com", email_verified=False)
        pendiente.hashed_password = "hash-viejo"
        mock_db.query.return_value.filter.return_value.first.return_value = pendiente

        resp = client.post("/auth/register", json={
            "email": "existe@test.com",
            "password": "password-nuevo",
            "name": "Nuevo",
            "accepted_terms": True,
        })

        assert resp.status_code == 200
        assert pendiente.hashed_password != "hash-viejo"
        assert pendiente.name == "Nuevo"
        assert pendiente.consent_accepted_at is not None

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


# ── DELETE /auth/me ───────────────────────────────────────────────────────────

class TestDeleteAccount:
    @patch("app.api.auth.verify_password", return_value=True)
    def test_elimina_la_cuenta_y_confirma_transaccion(self, mock_verify, client, mock_db, mock_user):
        resp = client.request("DELETE", "/auth/me", json={"password": "password123"})

        assert resp.status_code == 200
        mock_db.delete.assert_called_once_with(mock_user)
        mock_db.commit.assert_called_once()

    @patch("app.api.auth.verify_password", return_value=True)
    def test_borra_datos_personales_asociados(self, mock_verify, client, mock_db):
        from app.models.favorite import Favorite
        from app.models.recommendation_preference import RecommendationPreference
        from app.models.otp_code import OtpCode

        client.request("DELETE", "/auth/me", json={"password": "password123"})

        consultados = [c.args[0] for c in mock_db.query.call_args_list if c.args]
        assert any(c is Favorite for c in consultados)
        assert any(c is RecommendationPreference for c in consultados)
        assert any(c is OtpCode for c in consultados)

    @patch("app.api.auth.verify_password", return_value=True)
    def test_borra_las_viviendas_publicadas_por_el_usuario(self, mock_verify, client, mock_db):
        from app.models.property import Property
        mock_db.query.return_value.filter.return_value.all.return_value = [(7,), (8,)]

        client.request("DELETE", "/auth/me", json={"password": "password123"})

        consultados = [c.args[0] for c in mock_db.query.call_args_list if c.args]
        assert any(c is Property for c in consultados)
        assert mock_db.query.return_value.filter.return_value.delete.call_count >= 5

    @patch("app.api.auth.verify_password", return_value=False)
    def test_contrasena_incorrecta_retorna_400_y_no_borra(self, mock_verify, client, mock_db):
        resp = client.request("DELETE", "/auth/me", json={"password": "incorrecta"})

        assert resp.status_code == 400
        assert "incorrecta" in resp.json()["detail"]
        mock_db.delete.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch("app.api.auth.verify_password", return_value=True)
    def test_cuenta_admin_no_se_puede_eliminar(self, mock_verify, admin_client, mock_db):
        resp = admin_client.request("DELETE", "/auth/me", json={"password": "password123"})

        assert resp.status_code == 403
        mock_db.delete.assert_not_called()

    def test_sin_contrasena_retorna_422(self, client, mock_db):
        resp = client.request("DELETE", "/auth/me", json={})

        assert resp.status_code == 422
        mock_db.delete.assert_not_called()


# ── POST /auth/me/consent ─────────────────────────────────────────────────────

class TestAcceptConsent:
    def test_registra_fecha_y_version_para_usuarios_existentes(self, client, mock_user, mock_db):
        from app.core.privacy import PRIVACY_POLICY_VERSION
        mock_user.consent_accepted_at = None
        mock_user.consent_version = None

        resp = client.post("/auth/me/consent")

        assert resp.status_code == 200
        assert mock_user.consent_accepted_at is not None
        assert mock_user.consent_version == PRIVACY_POLICY_VERSION
        mock_db.commit.assert_called_once()
        assert resp.json()["consent_version"] == PRIVACY_POLICY_VERSION
