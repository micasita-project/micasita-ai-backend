"""
Pruebas unitarias para generar_recomendacion y _serialize_results.

Se mockea: DB (SQLAlchemy), get_osrm_route, recommender.predict y time.sleep.
No se conecta a la base de datos real ni a OSRM.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.recommendation_service import generar_recomendacion, _serialize_results

# Mismas columnas que genera el pipeline de entrenamiento
MODEL_COLUMNS = [
    "precio_alquiler",
    "area_m2",
    "presupuesto_usuario",
    "distancia_km_simulada",
    "tiempo_viaje_min",
    "modo_transporte_cycling",
    "modo_transporte_driving",
    "modo_transporte_walking",
]


# ─── helpers ─────────────────────────────────────────────────────────────────

def _make_property(pid, price, lat=-12.046, lon=-77.042, area=80.0, currency=None):
    p = MagicMock()
    p.id = pid
    p.price = price
    p.currency = currency
    p.latitude = lat
    p.longitude = lon
    p.total_area_sqm = area
    p.status = "approved"
    p.location = MagicMock()  # not None
    return p


def _make_db(rows_no_radius=None, rows_with_radius=None):
    """
    Devuelve un db mockeado que retorna `rows` al llamar .all() en la cadena
    de consulta de propiedades.

    rows: lista de tuplas (Property, dist_km) igual que la devuelve PostGIS.
    """
    db = MagicMock()
    rows_no_radius = rows_no_radius or []
    rows_with_radius = rows_with_radius or []

    # Sin max_distance_km: query.filter(...).order_by(...).all()
    chain_no_r = db.query.return_value.filter.return_value
    chain_no_r.order_by.return_value.all.return_value = rows_no_radius

    # Con max_distance_km: query.filter(...).filter(...).order_by(...).all()
    chain_with_r = db.query.return_value.filter.return_value.filter.return_value
    chain_with_r.order_by.return_value.all.return_value = rows_with_radius

    # Favoritos: query(Favorite.property_id).filter(...).all() → lista vacía
    chain_no_r.all.return_value = []

    return db


# ─── Casos de resultados vacíos ───────────────────────────────────────────────

class TestGenararRecomendacionSinResultados:
    def test_sin_propiedades_mensaje_generico(self):
        db = _make_db(rows_no_radius=[])
        result = generar_recomendacion(-12.046, -77.042, 1500, "driving", db)
        assert result["results"] == []
        assert result["total"] == 0
        assert "No hay viviendas" in result["message"]

    def test_sin_propiedades_en_radio_menciona_km(self):
        db = _make_db(rows_with_radius=[])
        result = generar_recomendacion(
            -12.046, -77.042, 1500, "driving", db, max_distance_km=10
        )
        assert "10 km" in result["message"]

    def test_todas_sobre_presupuesto_retorna_min_price(self):
        # Propiedad a 3000, usuario con 1000 → sobre presupuesto (incluso con 15% tolerancia)
        p = _make_property(1, price=3000.0)
        db = _make_db(rows_no_radius=[(p, 5.0)])
        result = generar_recomendacion(-12.046, -77.042, 1000, "driving", db)
        assert result["results"] == []
        assert result["min_price_in_area"] == pytest.approx(3000.0)
        assert "presupuesto" in result["message"]

    def test_presupuesto_con_tolerancia_15_porciento(self):
        # budget=1000, tolerancia=15% → límite=1150; propiedad a 1100 → entra
        p = _make_property(1, price=1100.0)
        with (
            patch("time.sleep"),
            patch("app.services.recommendation_service.predictor") as mock_pred,
            patch("app.services.recommendation_service.get_osrm_route", return_value=(3.0, 15.0)),
        ):
            mock_pred.predict_scores.return_value = [70.0]
            db = _make_db(rows_no_radius=[(p, 3.0)])
            result = generar_recomendacion(-12.046, -77.042, 1000, "driving", db)
        assert result["total"] == 1


# ─── Flujo normal con XGBoost mockeado ───────────────────────────────────────

class TestGenararRecomendacionFlujoNormal:
    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor")
    @patch("app.services.recommendation_service.get_osrm_route")
    def test_resultados_ordenados_por_score_descendente(
        self, mock_osrm, mock_pred, mock_sleep
    ):
        mock_osrm.return_value = (5.0, 20.0)
        mock_pred.predict_scores.return_value = [60.0, 80.0, 40.0]

        props = [
            _make_property(1, 1200.0),
            _make_property(2, 1000.0, lat=-12.060, lon=-77.050),
            _make_property(3, 1400.0, lat=-12.080, lon=-77.030),
        ]
        rows = [(p, float(i + 1)) for i, p in enumerate(props)]
        db = _make_db(rows_no_radius=rows)

        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        assert result["total"] == 3
        scores = [r["match_score"] for r in result["results"]]
        assert scores == sorted(scores, reverse=True)

    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor")
    @patch("app.services.recommendation_service.get_osrm_route")
    def test_scores_acotados_entre_0_y_100(self, mock_osrm, mock_pred, mock_sleep):
        mock_osrm.return_value = (5.0, 20.0)
        mock_pred.predict_scores.return_value = [150.0, -20.0]  # fuera de rango

        props = [
            _make_property(1, 1200.0),
            _make_property(2, 1000.0, lat=-12.060, lon=-77.050),
        ]
        rows = [(p, float(i + 1)) for i, p in enumerate(props)]
        db = _make_db(rows_no_radius=rows)

        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)
        for r in result["results"]:
            assert 0 <= r["match_score"] <= 100

    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor")
    @patch("app.services.recommendation_service.get_osrm_route")
    def test_time_saved_es_none_sin_casa_actual(self, mock_osrm, mock_pred, mock_sleep):
        mock_osrm.return_value = (5.0, 20.0)
        mock_pred.predict_scores.return_value = [70.0]

        db = _make_db(rows_no_radius=[(_make_property(1, 1200.0), 5.0)])
        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        # user_home_lat no pasado → time_saved_mins = None
        assert result["results"][0]["time_saved_mins"] is None

    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor")
    @patch("app.services.recommendation_service.get_osrm_route")
    def test_time_saved_calculado_con_casa_actual(self, mock_osrm, mock_pred, mock_sleep):
        # Primera llamada (commute actual): 40 min; segunda (vivienda candidata): 20 min
        mock_osrm.side_effect = [(0.0, 40.0), (5.0, 20.0)]
        mock_pred.predict_scores.return_value = [70.0]

        db = _make_db(rows_no_radius=[(_make_property(1, 1200.0), 5.0)])
        result = generar_recomendacion(
            -12.046, -77.042, 2000, "driving", db,
            user_home_lat=-12.100, user_home_lon=-77.000,
        )
        # time_saved = 40 - 20 = 20 min
        assert result["results"][0]["time_saved_mins"] == 20


# ─── Fallback a Haversine cuando OSRM falla ──────────────────────────────────

class TestFallbackHaversine:
    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor")
    @patch("app.services.recommendation_service.get_osrm_route")
    def test_osrm_falla_usa_haversine_y_devuelve_resultado(
        self, mock_osrm, mock_pred, mock_sleep
    ):
        mock_osrm.side_effect = Exception("Timeout: OSRM unreachable")
        mock_pred.predict_scores.return_value = [70.0]

        db = _make_db(rows_no_radius=[(_make_property(1, 1200.0), 5.0)])
        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        assert result["total"] == 1
        # Con dist_km=5.0 y driving → simulate_commute_time(5.0, 'driving')
        expected_time = round((5.0 * 1.4 / 15.0) * 60)
        assert result["results"][0]["predicted_time_min"] == expected_time


# ─── Circuit breaker ─────────────────────────────────────────────────────────

class TestCircuitBreaker:
    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor")
    @patch("app.services.recommendation_service.get_osrm_route")
    def test_deja_de_llamar_osrm_despues_de_5_fallos(
        self, mock_osrm, mock_pred, mock_sleep
    ):
        call_count = [0]

        def osrm_timeout(*args, **kwargs):
            call_count[0] += 1
            raise Exception("Timeout: OSRM unreachable")

        mock_osrm.side_effect = osrm_timeout
        mock_pred.predict_scores.return_value = [70.0] * 8

        props = [
            _make_property(i, 1200.0, lat=-12.046 - i * 0.01, lon=-77.042)
            for i in range(8)
        ]
        rows = [(p, float(i + 1)) for i, p in enumerate(props)]
        db = _make_db(rows_no_radius=rows)

        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        # Exactamente 5 llamadas reales a OSRM; las 3 restantes las corta el circuit breaker
        assert call_count[0] == 5
        # Todos los candidatos siguen devolviendo resultado (via Haversine fallback)
        assert result["total"] == 8


# ─── _serialize_results ───────────────────────────────────────────────────────

class TestSerializeResults:
    def _make_result(self, **kwargs):
        prop = MagicMock()
        prop.id = kwargs.get("pid", 1)
        prop.publisher_id = 2
        prop.title = kwargs.get("title", "Depto Miraflores")
        prop.property_type = "Departamento"
        prop.district = "Miraflores"
        prop.address = "Av. Larco 123"
        prop.latitude = -12.046
        prop.longitude = -77.042
        prop.currency = "PEN"
        prop.price = 1500.0
        prop.total_area_sqm = 80.0
        prop.covered_area_sqm = 70.0
        prop.bedrooms = 2
        prop.bathrooms = 1
        prop.parking = 0
        prop.antiquity = 5
        prop.description = "Descripción"
        prop.images = ["img.jpg"]
        prop.features = ["balcón"]
        prop.source_url = "http://example.com"
        prop.status = "approved"

        return {
            "property": prop,
            "match_score": kwargs.get("score", 85.0),
            "predicted_time_min": kwargs.get("time", 20),
            "time_saved_mins": kwargs.get("time_saved", 5),
        }

    def test_serializa_campos_basicos(self):
        serialized = _serialize_results([self._make_result(title="Casa Miraflores")])
        assert len(serialized) == 1
        assert serialized[0]["property"]["title"] == "Casa Miraflores"
        assert serialized[0]["match_score"] == 85.0
        assert serialized[0]["predicted_time_min"] == 20

    def test_time_saved_none_se_preserva(self):
        serialized = _serialize_results([self._make_result(time_saved=None)])
        assert serialized[0]["time_saved_mins"] is None

    def test_multiples_resultados_mantienen_orden(self):
        results = [self._make_result(score=s) for s in [90.0, 70.0, 50.0]]
        serialized = _serialize_results(results)
        scores = [r["match_score"] for r in serialized]
        assert scores == [90.0, 70.0, 50.0]

    def test_imagenes_vacias_se_serializa_como_lista(self):
        result = self._make_result()
        result["property"].images = []
        result["property"].features = []
        serialized = _serialize_results([result])
        assert serialized[0]["property"]["images"] == []
        assert serialized[0]["property"]["features"] == []
