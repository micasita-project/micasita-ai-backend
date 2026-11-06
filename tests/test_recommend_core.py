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
    corregir_tiempos_por_franja, FRANJAS_HORAS,
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
    @pytest.mark.parametrize("tiempo, esperado", [(0, 100), (45, 50), (90, 100 / 3)])
    def test_escala_fija(self, tiempo, esperado):
        assert calcular_match_score(tiempo) == pytest.approx(esperado)

    def test_viajes_largos_siguen_diferenciandose(self):
        assert 0 < calcular_match_score(180) < calcular_match_score(90) < 100

    def test_tiempo_negativo_se_acota_a_100(self):
        assert calcular_match_score(-1) == 100


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
        # Propiedad a 3000, usuario con 1000 → sobre presupuesto
        p = _make_property(1, price=3000.0)
        db = _make_db(rows_no_radius=[(p, 5.0)])
        result = generar_recomendacion(-12.046, -77.042, 1000, "driving", db)
        assert result["results"] == []
        assert result["min_price_in_area"] == pytest.approx(3000.0)
        assert "presupuesto" in result["message"]

    @pytest.mark.parametrize("precio, moneda, entra", [
        (999.99, "PEN", True),
        (1000.0, "PEN", True),
        (1000.01, "PEN", False),
        (1100.0, "PEN", False),
        (250.0, "USD", True),
        (250.01, "USD", False),
    ])
    @patch("app.services.recommendation_service.USD_TO_PEN", 4.0)
    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_table")
    def test_presupuesto_maximo_estricto(
        self, mock_osrm_table, mock_pred, precio, moneda, entra
    ):
        p = _make_property(1, price=precio, currency=moneda)
        mock_osrm_table.return_value = [(3.0, 15.0)]
        mock_pred.predict_minutes.return_value = [12.0] * 3
        db = _make_db(rows_no_radius=[(p, 3.0)])

        result = generar_recomendacion(-12.046, -77.042, 1000, "driving", db)

        assert result["total"] == int(entra)
        if entra:
            assert result["results"][0]["property"].id == p.id
        else:
            assert result["results"] == []
            assert result["min_price_in_area"] == pytest.approx(
                precio * (4.0 if moneda == "USD" else 1.0)
            )
            mock_osrm_table.assert_not_called()
            mock_pred.predict_minutes.assert_not_called()


# ─── Flujo normal con el modelo de tiempo mockeado ───────────────────────────

class TestGenararRecomendacionFlujoNormal:
    @pytest.mark.parametrize("tiempos, orden", [
        ([15.0, 16.0], [1, 2]),  # El precio nunca compensa un minuto más.
        ([15.1, 14.9], [2, 1]),  # Ambos muestran 15 min: gana el menor precio.
    ])
    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_table")
    def test_precio_solo_desempata_minutos_mostrados(
        self, mock_osrm_table, mock_pred, tiempos, orden
    ):
        mock_osrm_table.return_value = [(5.0, 20.0)] * 2
        mock_pred.predict_minutes.return_value = [t for t in tiempos for _ in range(3)]
        props = [_make_property(1, 1900.0), _make_property(2, 500.0)]
        db = _make_db(rows_no_radius=[(p, 5.0) for p in props])

        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        assert [r["property"].id for r in result["results"]] == orden
        if orden == [2, 1]:
            assert result["results"][0]["match_score"] == result["results"][1]["match_score"]

    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_table")
    def test_desempate_convierte_dolares_a_soles(self, mock_osrm_table, mock_pred):
        mock_osrm_table.return_value = [(5.0, 20.0)] * 2
        mock_pred.predict_minutes.return_value = [15.0] * 6
        props = [
            _make_property(1, 500.0, currency="USD"),
            _make_property(2, 1000.0, currency="PEN"),
        ]
        db = _make_db(rows_no_radius=[(p, 5.0) for p in props])

        result = generar_recomendacion(-12.046, -77.042, 3000, "driving", db)

        assert [r["property"].id for r in result["results"]] == [2, 1]

    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_table")
    def test_area_y_distancia_no_cambian_puntaje_a_igual_tiempo_y_precio(
        self, mock_osrm_table, mock_pred
    ):
        mock_osrm_table.return_value = [(1.0, 20.0), (20.0, 20.0)]
        mock_pred.predict_minutes.return_value = [20.0] * 6
        props = [
            _make_property(1, 1600.0, area=100.0),
            _make_property(2, 1600.0, area=10.0),
        ]
        props[0].bedrooms = 4
        props[1].bedrooms = 1
        db = _make_db(rows_no_radius=[(props[0], 1.0), (props[1], 20.0)])

        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        assert result["total"] == 2
        assert [r["match_score"] for r in result["results"]] == [69.2, 69.2]

    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_table")
    def test_mas_barata_rankea_primero_a_igual_tiempo(
        self, mock_osrm_table, mock_pred, mock_sleep
    ):
        # Mismo tiempo corregido para las tres; área y distancia favorecen
        # a la más cara, pero solo el precio debe decidir el orden.
        # Si el orden no sigue el precio, algo
        # rompió la orquestación entre generar_recomendacion y
        # calcular_match_score (no la fórmula en sí, que ya se prueba aparte).
        # get_osrm_table devuelve una fila por candidata, en el mismo orden.
        mock_osrm_table.return_value = [(5.0, 20.0), (20.0, 20.0), (1.0, 20.0)]
        # predict_minutes se llama UNA vez con el lote completo. Para driving,
        # cada candidata se expande a 3 filas (una por franja horaria), así que
        # el mock necesita 3 candidatas x 3 franjas = 9 valores, todos iguales
        # para que el tiempo corregido siga siendo el mismo para las tres.
        mock_pred.predict_minutes.return_value = [15.0] * 9

        props = [
            _make_property(1, 1200.0),   # precio S/ 1200
            _make_property(2, 1000.0, lat=-12.060, lon=-77.050, area=10.0),  # S/ 1000 — la más barata
            _make_property(3, 1400.0, lat=-12.080, lon=-77.030, area=100.0),  # S/ 1400 — la más cara
        ]
        rows = [(p, 5.0) for p in props]
        db = _make_db(rows_no_radius=rows)

        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        assert result["total"] == 3
        scores = [r["match_score"] for r in result["results"]]
        assert scores == [75.0, 75.0, 75.0]
        # La propiedad 2 (más barata) debe quedar primera; la 3 (más cara), última.
        ids_en_orden = [r["property"].id for r in result["results"]]
        assert ids_en_orden == [2, 1, 3]

    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_table")
    @patch("app.services.recommendation_service.get_osrm_route")
    def test_time_saved_es_none_sin_casa_actual(self, mock_osrm, mock_osrm_table, mock_pred, mock_sleep):
        mock_osrm.return_value = (5.0, 20.0)
        mock_osrm_table.return_value = [(5.0, 20.0)]
        # driving expande a 3 filas por candidata (una por franja horaria).
        mock_pred.predict_minutes.return_value = [15.0, 15.0, 15.0]

        db = _make_db(rows_no_radius=[(_make_property(1, 1200.0), 5.0)])
        result = generar_recomendacion(-12.046, -77.042, 2000, "driving", db)

        # user_home_lat no pasado → time_saved_mins = None
        assert result["results"][0]["time_saved_mins"] is None

    @patch("time.sleep")
    @patch("app.services.recommendation_service.predictor_travel_time")
    @patch("app.services.recommendation_service.get_osrm_table")
    @patch("app.services.recommendation_service.get_osrm_route")
    def test_time_saved_calculado_con_casa_actual(
        self, mock_osrm_route, mock_osrm_table, mock_pred, mock_sleep
    ):
        # get_osrm_route resuelve el commute actual (vivienda de hoy -> trabajo);
        # get_osrm_table resuelve en lote a las candidatas (aquí, una sola).
        # corregir_tiempos se invoca dos veces: una por cada lote real de OSRM.
        mock_osrm_route.return_value = (0.0, 40.0)
        mock_osrm_table.return_value = [(5.0, 20.0)]
        # Primera llamada: commute actual (1 fila, sin desglose por franja).
        # Segunda llamada: candidatas — driving expande a 3 filas (1 candidata
        # x 3 franjas), todas iguales para que el tiempo corregido siga en 20.
        mock_pred.predict_minutes.side_effect = [[40.0], [20.0, 20.0, 20.0]]

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


# ─── corregir_tiempos_por_franja ──────────────────────────────────────────────

FILA_BASE = {
    "osrm_min": 20.0, "osrm_dist_km": 5.0, "modo": "driving",
    "lat_a": -12.046, "lon_a": -77.042,
    "lat_b": -12.120, "lon_b": -77.030,
}


class TestCorregirTiemposPorFranja:
    @patch("app.services.recommendation_service.predictor_travel_time")
    def test_devuelve_las_3_franjas_para_driving(self, mock_pred):
        # Una sola llamada al modelo con las 3 filas (una por franja).
        mock_pred.predict_minutes.return_value = [22.0, 25.0, 30.0]
        resultado = corregir_tiempos_por_franja(FILA_BASE)
        assert set(resultado.keys()) == set(FRANJAS_HORAS.keys())
        assert resultado["punta_manana"] == 22.0
        assert resultado["valle"] == 25.0
        assert resultado["punta_tarde"] == 30.0
        mock_pred.predict_minutes.assert_called_once()
        filas_enviadas = mock_pred.predict_minutes.call_args[0][0]
        assert len(filas_enviadas) == 3
        horas_enviadas = {f["hora"] for f in filas_enviadas}
        assert horas_enviadas == set(FRANJAS_HORAS.values())

    @patch("app.services.recommendation_service.predictor_travel_time")
    def test_ninguna_franja_para_cycling(self, mock_pred):
        # Bici solo tiene una franja en el dataset ("valle"): no hay base para
        # ofrecer variación por hora sin extrapolar fuera de lo entrenado.
        fila = {**FILA_BASE, "modo": "cycling"}
        resultado = corregir_tiempos_por_franja(fila)
        assert resultado is None
        mock_pred.predict_minutes.assert_not_called()

    @patch("app.services.recommendation_service.predictor_travel_time")
    def test_ninguna_franja_para_walking(self, mock_pred):
        fila = {**FILA_BASE, "modo": "walking"}
        resultado = corregir_tiempos_por_franja(fila)
        assert resultado is None
        mock_pred.predict_minutes.assert_not_called()
