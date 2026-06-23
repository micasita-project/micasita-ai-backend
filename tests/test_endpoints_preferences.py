"""
Tests de endpoints de preferencias de recomendación:
  POST  /recommendation_preferences/
  GET   /recommendation_preferences/
  PATCH /recommendation_preferences/{id}
"""

from tests.conftest import make_workplace, make_pref

PREF_PAYLOAD = {
    "workplace_id": 1,
    "budget": 1500.0,
    "preferred_transportation": "driving",
    "max_distance_km": 10.0,
}


# ── POST /recommendation_preferences/ ────────────────────────────────────────

class TestCreatePreference:
    def _configure_db(self, mock_db, workplace=None, existing_pref=None):
        """Configura las dos consultas que hace el endpoint: workplace y pref existente."""
        results = [workplace, existing_pref]
        mock_db.query.return_value.filter.return_value.first.side_effect = results

    def test_crea_preferencia_exitosamente(self, client, mock_db):
        self._configure_db(mock_db, workplace=make_workplace(), existing_pref=None)
        resp = client.post("/recommendation_preferences/", json=PREF_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["budget"] == 1500.0
        assert data["preferred_transportation"] == "driving"

    def test_workplace_no_pertenece_al_usuario_retorna_404(self, client, mock_db):
        self._configure_db(mock_db, workplace=None, existing_pref=None)
        resp = client.post("/recommendation_preferences/", json=PREF_PAYLOAD)
        assert resp.status_code == 404
        assert "no autorizado" in resp.json()["detail"]

    def test_preferencia_duplicada_retorna_400(self, client, mock_db):
        self._configure_db(mock_db, workplace=make_workplace(), existing_pref=make_pref())
        resp = client.post("/recommendation_preferences/", json=PREF_PAYLOAD)
        assert resp.status_code == 400
        assert "Ya existen" in resp.json()["detail"]


# ── GET /recommendation_preferences/ ─────────────────────────────────────────

class TestListPreferences:
    def test_retorna_preferencias_del_usuario(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.all.return_value = [make_pref()]
        resp = client.get("/recommendation_preferences/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_filtra_por_workplace_id(self, client, mock_db):
        # Cuando se filtra por workplace_id hay dos .filter() encadenados
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = [make_pref()]
        resp = client.get("/recommendation_preferences/?workplace_id=1")
        assert resp.status_code == 200

    def test_lista_vacia_cuando_no_hay_preferencias(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.all.return_value = []
        resp = client.get("/recommendation_preferences/")
        assert resp.status_code == 200
        assert resp.json() == []


# ── PATCH /recommendation_preferences/{id} ────────────────────────────────────

class TestUpdatePreference:
    def test_actualiza_presupuesto(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = make_pref()
        resp = client.patch("/recommendation_preferences/1", json={"budget": 2000.0})
        assert resp.status_code == 200

    def test_preferencia_no_encontrada_retorna_404(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.patch("/recommendation_preferences/999", json={"budget": 2000.0})
        assert resp.status_code == 404

    def test_max_distance_km_mayor_a_50_retorna_422(self, client, mock_db):
        resp = client.patch("/recommendation_preferences/1", json={"max_distance_km": 99.0})
        assert resp.status_code == 422
