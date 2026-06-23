"""
Tests de la capa HTTP de los endpoints de recomendación.
La lógica de generar_recomendacion está cubierta en test_recommend_core.py.
Aquí se verifica el routing HTTP: 404, 400, guardado en historial, etc.
"""

import json
from unittest.mock import patch, MagicMock
from tests.conftest import make_workplace, make_pref, make_property, make_user

GUEST_PAYLOAD = {
    "work_lat": -12.046,
    "work_lon": -77.042,
    "budget": 1500.0,
    "preferred_transportation": "driving",
}

MOCK_RESULT = {
    "results": [],
    "total": 0,
    "message": "No hay viviendas disponibles en el sistema.",
    "min_price_in_area": None,
}


# ── POST /recommend/guest ─────────────────────────────────────────────────────

class TestGuestRecommend:
    @patch("app.api.recommend.generar_recomendacion", return_value=MOCK_RESULT)
    def test_devuelve_resultado_de_generar_recomendacion(self, mock_gen, client, mock_db):
        resp = client.post("/recommend/guest", json=GUEST_PAYLOAD)
        assert resp.status_code == 200
        mock_gen.assert_called_once()

    def test_payload_invalido_retorna_422(self, client):
        resp = client.post("/recommend/guest", json={"work_lat": -12.046})
        assert resp.status_code == 422


# ── POST /recommend/workplaces/{id}/generate ─────────────────────────────────

class TestGenerateRecommendations:
    def _setup_generate(self, mock_db, workplace=None, pref=None):
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            workplace,
            pref,
        ]

    @patch("app.api.recommend.generar_recomendacion")
    def test_genera_recomendaciones_y_guarda_historial(self, mock_gen, client, mock_db, mock_user):
        work = make_workplace()
        pref = make_pref()
        self._setup_generate(mock_db, workplace=work, pref=pref)

        prop = make_property(id=1)
        mock_gen.return_value = {
            "results": [{"property": prop, "match_score": 85.0, "predicted_time_min": 20, "time_saved_mins": None}],
            "total": 1,
            "message": None,
            "min_price_in_area": None,
        }

        resp = client.post("/recommend/workplaces/1/generate")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        # Verificar que se guardó en historial
        mock_db.add.assert_called_once()

    @patch("app.api.recommend.generar_recomendacion", return_value={
        "results": [], "total": 0, "message": "Sin resultados", "min_price_in_area": None,
    })
    def test_sin_resultados_no_guarda_historial(self, mock_gen, client, mock_db):
        work = make_workplace()
        pref = make_pref()
        self._setup_generate(mock_db, workplace=work, pref=pref)

        resp = client.post("/recommend/workplaces/1/generate")
        assert resp.status_code == 200
        mock_db.add.assert_not_called()

    def test_workplace_no_encontrado_retorna_404(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.post("/recommend/workplaces/999/generate")
        assert resp.status_code == 404

    def test_sin_preferencias_retorna_400(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            make_workplace(),
            None,  # sin preferencias
        ]
        resp = client.post("/recommend/workplaces/1/generate")
        assert resp.status_code == 400
        assert "preferencias" in resp.json()["detail"]


# ── GET /recommend/workplaces/{id}/latest ─────────────────────────────────────

class TestLatestRecommendations:
    def _make_history(self, results_list):
        from app.models.recommendation_history import RecommendationHistory
        h = RecommendationHistory()
        h.workplace_id = 1
        h.results = json.dumps(results_list)
        return h

    def test_retorna_ultima_recomendacion_guardada(self, client, mock_db):
        work = make_workplace()
        # El dict debe cumplir PropertyResponse (todos los campos requeridos)
        stored = [{
            "property": {
                "id": 1, "publisher_id": 2, "title": "Depto Test",
                "property_type": "Departamento", "district": "Miraflores",
                "address": "Av. Larco 123", "latitude": -12.046, "longitude": -77.042,
                "currency": "PEN", "price": 1500.0, "total_area_sqm": 80.0,
                "status": "approved", "is_favorite": False,
                "rejection_reason": None, "covered_area_sqm": None,
                "bedrooms": None, "bathrooms": None, "parking": None,
                "antiquity": None, "description": None, "images": [],
                "features": [], "source_url": None,
            },
            "match_score": 80.0,
            "predicted_time_min": 20.0,
            "time_saved_mins": None,
        }]
        history = self._make_history(stored)

        mock_db.query.return_value.filter.return_value.first.return_value = work
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = history
        # Favoritos vacíos
        mock_db.query.return_value.filter.return_value.all.return_value = []

        resp = client.get("/recommend/workplaces/1/latest")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_workplace_no_encontrado_retorna_404(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.get("/recommend/workplaces/999/latest")
        assert resp.status_code == 404

    def test_sin_historial_retorna_404(self, client, mock_db):
        work = make_workplace()
        mock_db.query.return_value.filter.return_value.first.return_value = work
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        resp = client.get("/recommend/workplaces/1/latest")
        assert resp.status_code == 404
        assert "Genera una primero" in resp.json()["detail"]


# ── GET /recommend/workplaces/{id}/history ────────────────────────────────────

class TestRecommendationHistory:
    def test_retorna_historial_ordenado(self, client, mock_db):
        from app.models.recommendation_history import RecommendationHistory
        import datetime

        work = make_workplace()
        mock_db.query.return_value.filter.return_value.first.return_value = work

        h1 = RecommendationHistory()
        h1.id = 1
        h1.workplace_id = 1
        h1.results = json.dumps([])
        h1.created_at = datetime.datetime(2024, 1, 2)

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [h1]

        resp = client.get("/recommend/workplaces/1/history")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["id"] == 1

    def test_workplace_no_encontrado_retorna_404(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.get("/recommend/workplaces/999/history")
        assert resp.status_code == 404
