"""
Tests de la capa HTTP de GET /route: el único punto de entrada que el front
debe usar para ruteo (tiempo + geometría). No requiere autenticación ni DB.
"""

from unittest.mock import patch

PARAMS = {
    "origin_lat": -12.0969, "origin_lon": -77.0367,
    "dest_lat": -12.1211, "dest_lon": -77.0295,
    "mode": "driving",
}


class TestGetRoute:
    @patch("app.api.route.corregir_tiempos")
    @patch("app.api.route.get_osrm_route_with_geometry")
    def test_osrm_exitoso_devuelve_tiempo_corregido_y_geometria(
        self, mock_osrm, mock_corregir, anon_client
    ):
        mock_osrm.return_value = (3.4, 15.0, [
            {"latitude": -12.0969, "longitude": -77.0367},
            {"latitude": -12.1211, "longitude": -77.0295},
        ])
        mock_corregir.return_value = [12.3]  # el modelo corrige 15.0 -> 12.3

        resp = anon_client.get("/route", params=PARAMS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["distance_km"] == 3.4
        assert data["duration_min"] == 12.3
        assert data["from_osrm"] is True
        assert len(data["waypoints"]) == 2
        # Sin pedir el desglose explícitamente, no debe calcularse.
        assert data["franjas"] is None

    @patch("app.api.route.corregir_tiempos_por_franja")
    @patch("app.api.route.corregir_tiempos")
    @patch("app.api.route.get_osrm_route_with_geometry")
    def test_franjas_true_incluye_el_desglose_horario(
        self, mock_osrm, mock_corregir, mock_por_franja, anon_client
    ):
        mock_osrm.return_value = (3.4, 15.0, [
            {"latitude": -12.0969, "longitude": -77.0367},
            {"latitude": -12.1211, "longitude": -77.0295},
        ])
        mock_corregir.return_value = [12.3]
        mock_por_franja.return_value = {"punta_manana": 12.3, "valle": 13.8, "punta_tarde": 16.8}

        resp = anon_client.get("/route", params={**PARAMS, "franjas": "true"})

        assert resp.status_code == 200
        assert resp.json()["franjas"] == {"punta_manana": 12.3, "valle": 13.8, "punta_tarde": 16.8}

    @patch("app.api.route.corregir_tiempos_por_franja")
    @patch("app.api.route.corregir_tiempos")
    @patch("app.api.route.get_osrm_route_with_geometry")
    def test_franjas_true_en_modo_sin_desglose_devuelve_null(
        self, mock_osrm, mock_corregir, mock_por_franja, anon_client
    ):
        # walking no tiene desglose horario válido (ver MODOS_CON_DESGLOSE_HORARIO
        # en recommendation_service.py) — corregir_tiempos_por_franja ya devuelve
        # None ahí; el endpoint solo debe respetarlo, no inventar nada.
        mock_osrm.return_value = (2.8, 30.0, [
            {"latitude": -12.0969, "longitude": -77.0367},
            {"latitude": -12.1211, "longitude": -77.0295},
        ])
        mock_corregir.return_value = [32.0]
        mock_por_franja.return_value = None

        resp = anon_client.get(
            "/route", params={**PARAMS, "mode": "walking", "franjas": "true"}
        )

        assert resp.status_code == 200
        assert resp.json()["franjas"] is None

    @patch("app.api.route.get_osrm_route_with_geometry")
    def test_osrm_falla_degrada_a_haversine_sin_romper_la_peticion(
        self, mock_osrm, anon_client
    ):
        mock_osrm.side_effect = Exception("Timeout: OSRM unreachable")

        resp = anon_client.get("/route", params=PARAMS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["from_osrm"] is False
        # Sin geometría real: solo origen y destino
        assert len(data["waypoints"]) == 2
        assert data["distance_km"] > 0
        assert data["duration_min"] > 0

    def test_modo_invalido_retorna_422(self, anon_client):
        params = {**PARAMS, "mode": "teletransporte"}
        resp = anon_client.get("/route", params=params)
        assert resp.status_code == 422

    def test_falta_parametro_retorna_422(self, anon_client):
        params = {k: v for k, v in PARAMS.items() if k != "dest_lat"}
        resp = anon_client.get("/route", params=params)
        assert resp.status_code == 422
