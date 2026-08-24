"""
Pruebas unitarias para generar_recomendacion, calcular_match_score y
_serialize_results.

Se mockea: DB (SQLAlchemy), get_osrm_route (commute actual), get_osrm_table
(candidatas, una sola llamada por lote), predictor_travel_time.predict_minutes
y time.sleep. No se conecta a la base de datos real, a OSRM ni carga el modelo
de ML — `predictor_travel_time` se mockea siempre que se ejercite el camino que
sí llama al modelo (candidatas resueltas por OSRM real).
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.recommendation_service import (
    generar_recomendacion, _serialize_results, calcular_match_score,
)


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


# ─── calcular_match_score: la función de utilidad, probada directamente ──────

class TestCalcularMatchScore:
    def test_acotado_entre_0_y_100_por_arriba(self):
        # Tiempo cero, muy barato, área grande → el máximo teórico supera 100
        score = calcular_match_score(tiempo_min=0, dist_km=0, precio_ratio=0.0, area_m2=100)
        assert score <= 100

    def test_acotado_entre_0_y_100_por_abajo(self):
        # Tiempo altísimo, muy caro, área diminuta → el mínimo teórico es negativo
        score = calcular_match_score(tiempo_min=500, dist_km=50, precio_ratio=10.0, area_m2=5)
        assert score >= 0

    def test_mas_barato_puntua_mas_alto_a_igualdad_de_lo_demas(self):
        barato = calcular_match_score(tiempo_min=20, dist_km=5, precio_ratio=0.5, area_m2=60)
        caro = calcular_match_score(tiempo_min=20, dist_km=5, precio_ratio=1.5, area_m2=60)
        assert barato > caro

    def test_mas_cerca_en_tiempo_puntua_mas_alto_a_igualdad_de_lo_demas(self):
        cerca = calcular_match_score(tiempo_min=10, dist_km=3, precio_ratio=0.8, area_m2=60)
        lejos = calcular_match_score(tiempo_min=60, dist_km=3, precio_ratio=0.8, area_m2=60)
        assert cerca > lejos

    def test_es_determinista(self):
        # A diferencia del viejo dataset_builder.py, no debe llevar ruido aleatorio
        a = calcular_match_score(tiempo_min=25, dist_km=6, precio_ratio=0.9, area_m2=45)
        b = calcular_match_score(tiempo_min=25, dist_km=6, precio_ratio=0.9, area_m2=45)
        assert a == b


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
            patch("app.services.recommendation_service.predictor_travel_time") as mock_pred,
            patch("app.services.recommendation_service.get_osrm_route", return_value=(3.0, 15.0)),
        ):
            mock_pred.predict_minutes.return_value = [12.0]
            db = _make_db(rows_no_radius=[(p, 3.0)])
            result = generar_recomendacion(-12.046, -77.042, 1000, "driving", db)
        assert result["total"] == 1


# ─── Flujo normal con el modelo de tiempo mockeado ───────────────────────────

class TestGenararRecomendacionFlujoNormal:
    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_table")
    def test_mas_barata_rankea_primero_a_igual_tiempo(
        self, mock_osrm_table, mock_pred, mock_sleep
    ):
        # Mismo tiempo corregido y misma distancia para las tres: la única
        # diferencia real es el precio. Si el orden no sigue el precio, algo
        # rompió la orquestación entre generar_recomendacion y
        # calcular_match_score (no la fórmula en sí, que ya se prueba aparte).
        # get_osrm_table devuelve una fila por candidata, en el mismo orden.
        mock_osrm_table.return_value = [(5.0, 20.0), (5.0, 20.0), (5.0, 20.0)]
        # Un valor por candidata: predict_minutes se llama UNA vez con el lote
        # completo, no una vez por propiedad.
        mock_pred.predict_minutes.return_value = [15.0, 15.0, 15.0]

        props = [
            _make_property(1, 1200.0),   # precio_ratio 0.60
            _make_property(2, 1000.0, lat=-12.060, lon=-77.050),  # 0.50 — la más barata
            _make_property(3, 1400.0, lat=-12.080, lon=-77.030),  # 0.70 — la más cara
        ]
        rows = [(p, 5.0) for p in props]
        db = _make_db(rows_no_radius=rows)

        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        assert result["total"] == 3
        scores = [r["match_score"] for r in result["results"]]
        assert scores == sorted(scores, reverse=True)
        # La propiedad 2 (más barata) debe quedar primera; la 3 (más cara), última.
        ids_en_orden = [r["property"].id for r in result["results"]]
        assert ids_en_orden == [2, 1, 3]

    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_route")
    def test_time_saved_es_none_sin_casa_actual(self, mock_osrm, mock_pred, mock_sleep):
        mock_osrm.return_value = (5.0, 20.0)
        mock_pred.predict_minutes.return_value = [15.0]

        db = _make_db(rows_no_radius=[(_make_property(1, 1200.0), 5.0)])
        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        # user_home_lat no pasado → time_saved_mins = None
        assert result["results"][0]["time_saved_mins"] is None

    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_route")
    def test_time_saved_calculado_con_casa_actual(self, mock_osrm, mock_pred, mock_sleep):
        # Primera llamada a OSRM (commute actual): 40 min; segunda (candidata): 20 min.
        # corregir_tiempos se invoca dos veces (una por cada llamada a OSRM real):
        # una para la vivienda actual, otra para el lote de candidatas.
        mock_osrm.side_effect = [(0.0, 40.0), (5.0, 20.0)]
        mock_pred.predict_minutes.side_effect = [[40.0], [20.0]]

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
    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_table")
    def test_osrm_falla_usa_haversine_y_devuelve_resultado(
        self, mock_osrm_table, mock_pred, mock_sleep
    ):
        mock_osrm_table.side_effect = Exception("Timeout: OSRM unreachable")

        db = _make_db(rows_no_radius=[(_make_property(1, 1200.0), 5.0)])
        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        assert result["total"] == 1
        # Con dist_km=5.0 y driving → simulate_commute_time(5.0, 'driving')
        expected_time = round((5.0 * 1.4 / 15.0) * 60)
        assert result["results"][0]["predicted_time_min"] == expected_time
        # El fallback de Haversine NUNCA debe pasar por el modelo: se entrenó
        # con salidas de OSRM, no con esta aproximación en línea recta.
        mock_pred.predict_minutes.assert_not_called()


# ─── Fallback de lote cuando OSRM /table falla entero ────────────────────────

class TestFallbackDeLote:
    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_table")
    def test_tabla_falla_completa_todas_caen_a_haversine_en_una_sola_llamada(
        self, mock_osrm_table, mock_pred, mock_sleep
    ):
        mock_osrm_table.side_effect = Exception("Timeout: OSRM unreachable")

        props = [
            _make_property(i, 1200.0, lat=-12.046 - i * 0.01, lon=-77.042)
            for i in range(8)
        ]
        rows = [(p, float(i + 1)) for i, p in enumerate(props)]
        db = _make_db(rows_no_radius=rows)

        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        # Ya no hay circuit breaker por candidata: es una sola llamada a /table
        # para las 8 a la vez, así que si falla, falla una única vez.
        assert mock_osrm_table.call_count == 1
        # Todos los candidatos siguen devolviendo resultado (via Haversine fallback)
        assert result["total"] == 8
        # Ninguno vino de OSRM real, así que el modelo nunca debió invocarse
        mock_pred.predict_minutes.assert_not_called()


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
        prop.phone = kwargs.get("phone", "999888777")

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

    def test_incluye_phone(self):
        # /generate lo devuelve vía PropertyResponse, pero /latest lee de acá —
        # si no se serializa, el botón de WhatsApp se rompe tras un reload.
        serialized = _serialize_results([self._make_result(phone="987654321")])
        assert serialized[0]["property"]["phone"] == "987654321"

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
