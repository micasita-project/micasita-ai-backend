import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve(
).parents[1] / "scripts" / "scraper_viviendas" / "scraper_clean.py"
SPEC = importlib.util.spec_from_file_location("scraper_clean", MODULE_PATH)
scraper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scraper)


def test_parse_jsonld_data_extracts_phone_and_core_fields():
    html = """
    <html><head>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Apartment",
      "name": "Departamento en alquiler",
      "description": "Hermoso departamento",
      "telephone": "51 9 37655229",
      "floorSize": {"value": 55, "unitText": "m²"},
      "numberOfBedrooms": 2,
      "numberOfBathroomsTotal": 2,
      "address": {"streetAddress": "Av. Siempre Viva 123", "addressLocality": "Lima", "addressRegion": "Lima"},
      "geo": {"latitude": -12.1, "longitude": -77.0},
      "image": ["https://img1.jpg", "https://img2.jpg"]
    }
    </script>
    </head></html>
    """

    data = scraper.parse_jsonld_data(html)

    assert "title" not in data
    assert data["description"] == "Hermoso departamento"
    assert data["phone"] == "937655229"
    assert data["total_area_sqm"] == 55.0
    assert data["bedrooms"] == 2
    assert data["bathrooms"] == 2
    assert data["latitude"] == -12.1
    assert data["longitude"] == -77.0
    assert data["images"] == ["https://img1.jpg", "https://img2.jpg"]


def test_format_phone_returns_human_readable_value():
    assert scraper.format_phone("51 9 37655229") == "51 937 655 229"
    assert scraper.format_phone("937655229") == "51 937 655 229"
