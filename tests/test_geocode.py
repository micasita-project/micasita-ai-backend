"""
Pruebas unitarias para app/api/geocode.py:
  - _photon_display_name → función pura (sin HTTP)
  - _photon_search       → llama a la API de Photon (mockeado)
  - _photon_reverse      → llama a la API de Photon (mockeado)
  - _fetch_search        → caché + fallback a Photon cuando Nominatim devuelve None
  - _fetch_reverse       → caché + fallback a Photon cuando Nominatim devuelve None
"""

import pytest
from unittest.mock import patch, MagicMock

import app.api.geocode as geocode_module
from app.api.geocode import _photon_display_name, _photon_search, _photon_reverse


@pytest.fixture(autouse=True)
def limpiar_caches():
    """Reinicia el caché in-memory entre tests para evitar contaminación."""
    geocode_module._search_cache.clear()
    geocode_module._reverse_cache.clear()
    yield
    geocode_module._search_cache.clear()
    geocode_module._reverse_cache.clear()


# ─── _photon_display_name ────────────────────────────────────────────────────

class TestPhotonDisplayName:
    def test_combina_nombre_y_calle(self):
        props = {"name": "Parque Kennedy", "street": "Larco", "city": "Lima"}
        result = _photon_display_name(props)
        assert "Parque Kennedy" in result
        assert "Larco" in result

    def test_deduplica_valores_repetidos(self):
        # Si "Lima" aparece en "name" y "city", sólo debe salir una vez
        props = {"name": "Lima", "city": "Lima"}
        result = _photon_display_name(props)
        assert result.count("Lima") == 1

    def test_props_vacias_retorna_fallback(self):
        assert _photon_display_name({}) == "Ubicación encontrada"

    def test_omite_valores_none(self):
        props = {"name": "Miraflores", "street": None, "city": "Lima"}
        result = _photon_display_name(props)
        assert "None" not in result

    def test_solo_housenumber_no_da_vacio(self):
        props = {"housenumber": "123"}
        result = _photon_display_name(props)
        assert "123" in result


# ─── _photon_search ───────────────────────────────────────────────────────────

class TestPhotonSearch:
    @patch("app.api.geocode.requests.get")
    def test_filtra_resultados_fuera_de_peru(self, mock_get):
        mock_get.return_value.json.return_value = {
            "features": [
                {"properties": {"countrycode": "PE", "name": "Lima"}},
                {"properties": {"countrycode": "AR", "name": "Buenos Aires"}},
                {"properties": {"countrycode": "CL", "name": "Santiago"}},
            ]
        }
        results = _photon_search("Lima", limit=5)
        assert len(results) == 1
        assert results[0]["properties"]["name"] == "Lima"

    @patch("app.api.geocode.requests.get")
    def test_countrycode_minusculas_tambien_pasa(self, mock_get):
        mock_get.return_value.json.return_value = {
            "features": [
                {"properties": {"countrycode": "pe", "name": "Callao"}},
            ]
        }
        results = _photon_search("Callao", limit=5)
        assert len(results) == 1

    @patch("app.api.geocode.requests.get")
    def test_respeta_el_limite(self, mock_get):
        mock_get.return_value.json.return_value = {
            "features": [
                {"properties": {"countrycode": "PE", "name": f"Lugar {i}"}}
                for i in range(10)
            ]
        }
        results = _photon_search("Lima", limit=3)
        assert len(results) == 3

    @patch("app.api.geocode.requests.get")
    def test_retorna_lista_vacia_si_falla_la_request(self, mock_get):
        mock_get.side_effect = Exception("Connection error")
        results = _photon_search("Lima", limit=5)
        assert results == []


# ─── _photon_reverse ─────────────────────────────────────────────────────────

class TestPhotonReverse:
    @patch("app.api.geocode.requests.get")
    def test_retorna_properties_del_primer_feature(self, mock_get):
        mock_get.return_value.json.return_value = {
            "features": [{"properties": {"name": "Miraflores", "city": "Lima"}}]
        }
        result = _photon_reverse(-12.046, -77.042)
        assert result["name"] == "Miraflores"

    @patch("app.api.geocode.requests.get")
    def test_retorna_dict_vacio_si_no_hay_features(self, mock_get):
        mock_get.return_value.json.return_value = {"features": []}
        result = _photon_reverse(-12.046, -77.042)
        assert result == {}

    @patch("app.api.geocode.requests.get")
    def test_retorna_dict_vacio_si_falla_la_request(self, mock_get):
        mock_get.side_effect = Exception("Timeout")
        result = _photon_reverse(-12.046, -77.042)
        assert result == {}


# ─── Caché de búsqueda ────────────────────────────────────────────────────────

class TestSearchCache:
    @patch("app.api.geocode._nominatim_get")
    def test_segunda_llamada_usa_cache_y_no_llama_nominatim(self, mock_nom):
        mock_nom.return_value.json.return_value = [{"display_name": "Lima, Peru"}]

        geocode_module._fetch_search("miraflores", 5)
        geocode_module._fetch_search("miraflores", 5)

        assert mock_nom.call_count == 1

    @patch("app.api.geocode._nominatim_get")
    def test_queries_distintas_no_comparten_cache(self, mock_nom):
        mock_nom.return_value.json.return_value = [{"display_name": "Resultado"}]

        geocode_module._fetch_search("miraflores", 5)
        geocode_module._fetch_search("san isidro", 5)

        assert mock_nom.call_count == 2

    @patch("app.api.geocode._photon_search")
    @patch("app.api.geocode._nominatim_get")
    def test_fallback_a_photon_cuando_nominatim_devuelve_none(
        self, mock_nom, mock_photon
    ):
        mock_nom.return_value = None  # Simula 429
        mock_photon.return_value = [{"properties": {"countrycode": "PE", "name": "Lima"}}]

        result = geocode_module._fetch_search("lima", 5)

        mock_photon.assert_called_once()
        assert result[0]["properties"]["name"] == "Lima"


# ─── Caché de geocodificación inversa ────────────────────────────────────────

class TestReverseCache:
    @patch("app.api.geocode._nominatim_get")
    def test_segunda_llamada_usa_cache(self, mock_nom):
        mock_nom.return_value.json.return_value = {
            "display_name": "Miraflores, Lima, Perú",
            "type": "suburb",
        }

        geocode_module._fetch_reverse(-12.046, -77.042)
        geocode_module._fetch_reverse(-12.046, -77.042)

        assert mock_nom.call_count == 1

    @patch("app.api.geocode._photon_reverse")
    @patch("app.api.geocode._nominatim_get")
    def test_fallback_a_photon_cuando_nominatim_devuelve_none(
        self, mock_nom, mock_photon
    ):
        mock_nom.return_value = None  # 429
        mock_photon.return_value = {"name": "Miraflores"}

        result = geocode_module._fetch_reverse(-12.046, -77.042)

        mock_photon.assert_called_once()
        assert result["name"] == "Miraflores"

    @patch("app.api.geocode._nominatim_get")
    def test_no_cachea_respuesta_sin_display_name(self, mock_nom):
        # Nominatim devuelve algo pero sin display_name → no debe cachearse
        mock_nom.return_value.json.return_value = {"type": "node"}  # sin display_name

        geocode_module._fetch_reverse(-12.046, -77.042)
        geocode_module._fetch_reverse(-12.046, -77.042)

        # Debe llamar 2 veces porque no se cacheó
        assert mock_nom.call_count == 2
