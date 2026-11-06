"""Los scripts de reconstrucción deben rechazar destinos ajenos a las bases locales."""
import pytest

from scripts.local_database import local_url


@pytest.mark.parametrize("url", [
    "postgresql://user:pass@production.example/micasita_db",
    "postgresql://user:pass@localhost/another_database",
    "postgresql://user:pass@localhost/micasita_db?host=production.example",
    "sqlite:///micasita_db",
])
def test_rejects_nonlocal_or_unexpected_database(url):
    with pytest.raises(ValueError):
        local_url(url)


@pytest.mark.parametrize("database", ["micasita_db", "micasita_e2e"])
def test_accepts_known_local_database(database):
    assert local_url(f"postgresql://user:pass@127.0.0.1:5432/{database}").database == database
