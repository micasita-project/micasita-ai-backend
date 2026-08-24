"""
Pruebas unitarias para las funciones auxiliares de recommend.py:
  - haversine        → fórmula geométrica pura
  - simulate_commute_time → fallback de tiempo cuando OSRM falla
  - _to_pen          → conversión de moneda
  - get_osrm_route   → cliente HTTP (con requests mockeado)
"""

import pytest
import requests as requests_lib
from unittest.mock import patch, MagicMock

from app.services.recommendation_service import (
    haversine,
    simulate_commute_time,
    _to_pen,
    get_osrm_route,
    USD_TO_PEN,
)


# ─── haversine ────────────────────────────────────────────────────────────────

class TestHaversine:
    def test_mismo_punto_es_cero(self):
        assert haversine(-12.046, -77.042, -12.046, -77.042) == pytest.approx(0.0, abs=1e-6)

    def test_positivo_para_puntos_distintos(self):
        assert haversine(-12.046, -77.042, -12.120, -77.030) > 0

    def test_simetrico(self):
        d1 = haversine(-12.046, -77.042, -12.120, -77.030)
        d2 = haversine(-12.120, -77.030, -12.046, -77.042)
        assert d1 == pytest.approx(d2, abs=1e-6)

    def test_distancia_conocida_lima(self):
        # Miraflores (-12.119, -77.029) → Callao (-12.056, -77.131): ~12-14 km en línea recta
        dist = haversine(-12.119, -77.029, -12.056, -77.131)
        assert 10.0 < dist < 16.0

    def test_proporcional_a_la_latitud(self):
        # Mover 1 grado de latitud ≈ 111 km
        dist = haversine(0.0, 0.0, 1.0, 0.0)
        assert 110.0 < dist < 112.0


# ─── simulate_commute_time ────────────────────────────────────────────────────

class TestSimulateCommuteTime:
    def test_walking_usa_4_5_kmh(self):
        expected = (1.0 * 1.4 / 4.5) * 60
        assert simulate_commute_time(1.0, "walking") == pytest.approx(expected, rel=1e-6)

    def test_cycling_usa_12_kmh(self):
        expected = (1.0 * 1.4 / 12.0) * 60
        assert simulate_commute_time(1.0, "cycling") == pytest.approx(expected, rel=1e-6)

    def test_driving_usa_15_kmh(self):
        expected = (1.0 * 1.4 / 15.0) * 60
        assert simulate_commute_time(1.0, "driving") == pytest.approx(expected, rel=1e-6)

    def test_alias_espanol_caminando(self):
        assert simulate_commute_time(5.0, "caminando") == pytest.approx(
            simulate_commute_time(5.0, "walking")
        )

    def test_alias_espanol_bicicleta(self):
        assert simulate_commute_time(5.0, "bicicleta") == pytest.approx(
            simulate_commute_time(5.0, "cycling")
        )

    def test_insensible_a_mayusculas(self):
        assert simulate_commute_time(5.0, "WALKING") == pytest.approx(
            simulate_commute_time(5.0, "walking")
        )

    def test_walking_mas_lento_que_cycling(self):
        assert simulate_commute_time(5.0, "walking") > simulate_commute_time(5.0, "cycling")

    def test_cycling_mas_lento_que_driving(self):
        assert simulate_commute_time(5.0, "cycling") > simulate_commute_time(5.0, "driving")

    def test_distancia_cero_retorna_cero(self):
        assert simulate_commute_time(0.0, "walking") == 0.0

    def test_proporcional_a_distancia(self):
        assert simulate_commute_time(10.0, "driving") == pytest.approx(
            2 * simulate_commute_time(5.0, "driving")
        )


# ─── _to_pen ─────────────────────────────────────────────────────────────────

class TestToPen:
    def test_usd_se_multiplica_por_tipo_de_cambio(self):
        assert _to_pen(100.0, "USD") == pytest.approx(100.0 * USD_TO_PEN)

    def test_usd_insensible_a_mayusculas(self):
        assert _to_pen(100.0, "usd") == pytest.approx(_to_pen(100.0, "USD"))

    def test_pen_no_cambia(self):
        assert _to_pen(500.0, "PEN") == 500.0

    def test_currency_none_no_cambia(self):
        assert _to_pen(500.0, None) == 500.0

    def test_precio_cero(self):
        assert _to_pen(0.0, "USD") == 0.0


# ─── get_osrm_route ───────────────────────────────────────────────────────────

def _mock_osrm_ok(distance_m: float, duration_s: float) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "code": "Ok",
        "routes": [{"distance": distance_m, "duration": duration_s}],
    }
    return resp


class TestGetOsrmRoute:
    @patch("app.services.recommendation_service.requests.get")
    def test_retorna_distancia_y_tiempo_correctos(self, mock_get):
        mock_get.return_value = _mock_osrm_ok(5000, 600)  # 5 km, 10 min
        dist, tiempo = get_osrm_route(-12.046, -77.042, -12.120, -77.030, "driving")
        assert dist == pytest.approx(5.0, rel=1e-3)
        assert tiempo == pytest.approx(10.0, rel=1e-3)

    # OSRM_BASE_URLS ahora sale de settings (lee .env real) en vez de un
    # default fijo en el módulo — se fija explícitamente a los defaults
    # públicos para que el test no dependa de lo que tenga el .env local
    # (p. ej. un OSRM propio apuntado a localhost para desarrollo).
    _DEFAULT_URLS = {
        "driving": "https://routing.openstreetmap.de/routed-car/route/v1/driving",
        "cycling": "https://routing.openstreetmap.de/routed-bike/route/v1/driving",
        "walking": "https://routing.openstreetmap.de/routed-foot/route/v1/driving",
    }

    @patch("app.services.recommendation_service.OSRM_BASE_URLS", _DEFAULT_URLS)
    @patch("app.services.recommendation_service.requests.get")
    def test_driving_llama_routed_car(self, mock_get):
        mock_get.return_value = _mock_osrm_ok(5000, 600)
        get_osrm_route(-12.046, -77.042, -12.120, -77.030, "driving")
        assert "routed-car" in mock_get.call_args[0][0]

    @patch("app.services.recommendation_service.OSRM_BASE_URLS", _DEFAULT_URLS)
    @patch("app.services.recommendation_service.requests.get")
    def test_cycling_llama_routed_bike(self, mock_get):
        mock_get.return_value = _mock_osrm_ok(3000, 900)
        get_osrm_route(-12.046, -77.042, -12.120, -77.030, "cycling")
        assert "routed-bike" in mock_get.call_args[0][0]

    @patch("app.services.recommendation_service.OSRM_BASE_URLS", _DEFAULT_URLS)
    @patch("app.services.recommendation_service.requests.get")
    def test_walking_llama_routed_foot(self, mock_get):
        mock_get.return_value = _mock_osrm_ok(2000, 1800)
        get_osrm_route(-12.046, -77.042, -12.120, -77.030, "walking")
        assert "routed-foot" in mock_get.call_args[0][0]

    @patch("app.services.recommendation_service.requests.get")
    def test_lanza_value_error_sin_rutas(self, mock_get):
        mock_get.return_value.json.return_value = {"code": "Ok", "routes": []}
        with pytest.raises(ValueError, match="No route found"):
            get_osrm_route(-12.046, -77.042, -12.120, -77.030, "driving")

    @patch("app.services.recommendation_service.requests.get")
    def test_lanza_value_error_cuando_code_no_es_ok(self, mock_get):
        mock_get.return_value.json.return_value = {"code": "NoSegment", "routes": []}
        with pytest.raises(ValueError, match="No route found"):
            get_osrm_route(-12.046, -77.042, -12.120, -77.030, "driving")

    @patch("app.services.recommendation_service.requests.get")
    def test_propaga_http_error(self, mock_get):
        mock_get.return_value.raise_for_status.side_effect = requests_lib.HTTPError("503")
        with pytest.raises(requests_lib.HTTPError):
            get_osrm_route(-12.046, -77.042, -12.120, -77.030, "driving")

    @patch("app.services.recommendation_service.requests.get")
    def test_coordenadas_van_en_orden_lon_lat(self, mock_get):
        mock_get.return_value = _mock_osrm_ok(1000, 120)
        get_osrm_route(-12.046, -77.042, -12.120, -77.030, "driving")
        url_called = mock_get.call_args[0][0]
        # OSRM espera lon,lat — la longitud (−77) debe aparecer antes que la latitud (−12)
        assert "-77.042,-12.046" in url_called
