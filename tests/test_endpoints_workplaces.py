"""
Tests de endpoints de workplaces:
  POST   /workplaces/
  GET    /workplaces/
  PATCH  /workplaces/{id}
  DELETE /workplaces/{id}
"""

from tests.conftest import make_workplace

LIMA_COORDS = {"work_lat": -12.046, "work_lon": -77.042, "work_address": "Av. Larco 123"}
OUT_COORDS = {"work_lat": -16.0, "work_lon": -71.5, "work_address": "Fuera de Lima"}


# ── POST /workplaces/ ─────────────────────────────────────────────────────────

class TestCreateWorkplace:
    def test_crea_workplace_en_lima(self, client, mock_db):
        resp = client.post("/workplaces/", json=LIMA_COORDS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["work_address"] == LIMA_COORDS["work_address"]
        assert data["work_lat"] == LIMA_COORDS["work_lat"]

    def test_coordenadas_fuera_de_lima_retorna_400(self, client, mock_db):
        resp = client.post("/workplaces/", json=OUT_COORDS)
        assert resp.status_code == 400
        assert "Lima" in resp.json()["detail"]


# ── GET /workplaces/ ──────────────────────────────────────────────────────────

class TestListWorkplaces:
    def test_retorna_lista_de_workplaces(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.all.return_value = [
            make_workplace(id=1),
            make_workplace(id=2),
        ]
        resp = client.get("/workplaces/")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_lista_vacia_cuando_no_hay_workplaces(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.all.return_value = []
        resp = client.get("/workplaces/")
        assert resp.status_code == 200
        assert resp.json() == []


# ── PATCH /workplaces/{id} ────────────────────────────────────────────────────

class TestUpdateWorkplace:
    def test_actualiza_direccion(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = make_workplace()
        resp = client.patch("/workplaces/1", json={"work_address": "Nueva Dir"})
        assert resp.status_code == 200

    def test_workplace_no_encontrado_retorna_404(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.patch("/workplaces/999", json={"work_address": "X"})
        assert resp.status_code == 404

    def test_actualizar_coords_fuera_de_lima_retorna_400(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = make_workplace()
        resp = client.patch("/workplaces/1", json={"work_lat": -16.0, "work_lon": -71.5})
        assert resp.status_code == 400
        assert "Lima" in resp.json()["detail"]

    def test_actualizar_solo_lat_valida_par_con_lon_actual(self, client, mock_db):
        # Cambiar solo lat a valor dentro de Lima no debe fallar
        mock_db.query.return_value.filter.return_value.first.return_value = make_workplace()
        resp = client.patch("/workplaces/1", json={"work_lat": -12.100})
        assert resp.status_code == 200


# ── DELETE /workplaces/{id} ───────────────────────────────────────────────────

class TestDeleteWorkplace:
    def test_elimina_workplace_existente(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = make_workplace()
        resp = client.delete("/workplaces/1")
        assert resp.status_code == 204
        mock_db.delete.assert_called_once()

    def test_workplace_no_encontrado_retorna_404(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.delete("/workplaces/999")
        assert resp.status_code == 404
