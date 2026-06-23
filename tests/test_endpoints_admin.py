"""
Tests de endpoints de administración:
  GET   /admin/properties/pending
  PATCH /admin/properties/{id}/status
  GET   /admin/users
  PATCH /admin/users/{id}/status
"""

from unittest.mock import patch
from tests.conftest import make_property, make_user


# ── GET /admin/properties/pending ─────────────────────────────────────────────

class TestPendingProperties:
    def test_retorna_propiedades_pendientes(self, admin_client, mock_db):
        pending = [make_property(id=i, status="pending") for i in range(1, 4)]
        mock_db.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = pending
        resp = admin_client.get("/admin/properties/pending")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_usuario_normal_no_puede_acceder(self, client, mock_db):
        resp = client.get("/admin/properties/pending")
        assert resp.status_code == 403


# ── PATCH /admin/properties/{id}/status ──────────────────────────────────────

class TestUpdatePropertyStatus:
    @patch("app.api.admin.email_service")
    def test_aprueba_propiedad(self, mock_email, admin_client, mock_db):
        prop = make_property(id=1, status="pending")
        owner = make_user(id=prop.publisher_id)
        mock_db.query.return_value.filter.return_value.first.side_effect = [prop, owner]

        resp = admin_client.patch("/admin/properties/1/status", json={"status": "approved"})
        assert resp.status_code == 200
        assert prop.status == "approved"
        assert prop.rejection_reason is None

    @patch("app.api.admin.email_service")
    def test_rechaza_propiedad_con_motivo(self, mock_email, admin_client, mock_db):
        prop = make_property(id=1, status="pending")
        owner = make_user(id=prop.publisher_id)
        mock_db.query.return_value.filter.return_value.first.side_effect = [prop, owner]

        resp = admin_client.patch("/admin/properties/1/status", json={
            "status": "rejected",
            "rejection_reason": "Imágenes insuficientes",
        })
        assert resp.status_code == 200
        assert prop.rejection_reason == "Imágenes insuficientes"

    def test_rechazo_sin_motivo_retorna_400(self, admin_client, mock_db):
        prop = make_property(id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = prop

        resp = admin_client.patch("/admin/properties/1/status", json={
            "status": "rejected",
            "rejection_reason": "",
        })
        assert resp.status_code == 400
        assert "rejection_reason" in resp.json()["detail"]

    def test_estado_invalido_retorna_400(self, admin_client, mock_db):
        prop = make_property(id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = prop

        resp = admin_client.patch("/admin/properties/1/status", json={"status": "publicada"})
        assert resp.status_code == 400

    def test_propiedad_no_encontrada_retorna_404(self, admin_client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = admin_client.patch("/admin/properties/999/status", json={"status": "approved"})
        assert resp.status_code == 404


# ── GET /admin/users ──────────────────────────────────────────────────────────

class TestListUsers:
    def test_retorna_todos_los_usuarios(self, admin_client, mock_db):
        users = [make_user(id=i, email=f"u{i}@test.com") for i in range(1, 4)]
        mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = users
        resp = admin_client.get("/admin/users")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_busqueda_por_email_aplica_filtro(self, admin_client, mock_db):
        # Con search, hay un .filter() extra
        users = [make_user(id=1, email="jose@test.com")]
        mock_db.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = users
        resp = admin_client.get("/admin/users?search=jose")
        assert resp.status_code == 200

    def test_usuario_normal_no_puede_acceder(self, client):
        resp = client.get("/admin/users")
        assert resp.status_code == 403


# ── PATCH /admin/users/{id}/status ────────────────────────────────────────────

class TestUpdateUserStatus:
    @patch("app.api.admin.email_service")
    def test_bloquea_usuario(self, mock_email, admin_client, mock_db, mock_admin):
        user = make_user(id=5, email="victim@test.com")
        mock_db.query.return_value.filter.return_value.first.return_value = user

        resp = admin_client.patch("/admin/users/5/status", json={"is_active": False})
        assert resp.status_code == 200
        assert user.is_active is False
        # Verifica que las propiedades del usuario se ocultaron
        mock_db.query.return_value.filter.return_value.update.assert_called_once()

    @patch("app.api.admin.email_service")
    def test_reactiva_usuario(self, mock_email, admin_client, mock_db):
        user = make_user(id=5, is_active=False)
        mock_db.query.return_value.filter.return_value.first.return_value = user

        resp = admin_client.patch("/admin/users/5/status", json={"is_active": True})
        assert resp.status_code == 200
        assert user.is_active is True

    def test_admin_no_puede_bloquearse_a_si_mismo(self, admin_client, mock_db, mock_admin):
        mock_db.query.return_value.filter.return_value.first.return_value = mock_admin

        resp = admin_client.patch(f"/admin/users/{mock_admin.id}/status", json={"is_active": False})
        assert resp.status_code == 400
        assert "ti mismo" in resp.json()["detail"]

    def test_usuario_no_encontrado_retorna_404(self, admin_client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = admin_client.patch("/admin/users/999/status", json={"is_active": False})
        assert resp.status_code == 404
