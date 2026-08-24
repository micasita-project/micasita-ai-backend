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
