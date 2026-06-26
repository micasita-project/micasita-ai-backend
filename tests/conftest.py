import os
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Env vars de relleno para que pydantic-settings no falle al importar módulos ──
# Se aplican ANTES de cualquier import de app.* para evitar ValidationError.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_unit.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-only-for-unit-tests")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test")
os.environ.setdefault("CLOUDINARY_API_KEY", "test")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test")
os.environ.setdefault("RESEND_API_KEY", "test")
os.environ.setdefault("RESEND_EMAIL_SENDER", "test@test.com")


# ── Helpers para crear instancias de modelos sin sesión de DB real ────────────

def make_user(id=1, email="user@test.com", role="user", is_active=True, email_verified=True):
    from app.models.user import User
    u = User()
    u.id = id
    u.email = email
    u.role = role
    u.is_active = is_active
    u.email_verified = email_verified
    u.name = "Test"
    u.last_name = "User"
    u.home_lat = None
    u.home_lon = None
    u.home_address = None
    return u


def make_workplace(id=1, user_id=1):
    from app.models.workplace import Workplace
    w = Workplace()
    w.id = id
    w.user_id = user_id
    w.work_address = "Av. Larco 123, Miraflores"
    w.work_lat = -12.046
    w.work_lon = -77.042
    return w


def make_property(id=1, publisher_id=1, status="approved"):
    from app.models.property import Property
    p = Property()
    p.id = id
    p.publisher_id = publisher_id
    p.title = "Depto Test"
    p.property_type = "Departamento"
    p.district = "Miraflores"
    p.address = "Calle Test 123"
    p.latitude = -12.046
    p.longitude = -77.042
    p.currency = "PEN"
    p.price = 1500.0
    p.total_area_sqm = 80.0
    p.covered_area_sqm = 70.0
    p.bedrooms = 2
    p.bathrooms = 1
    p.parking = 0
    p.antiquity = None
    p.description = "Descripción de prueba"
    p.images = []
    p.features = []
    p.source_url = None
    p.status = status
    p.rejection_reason = None
    p.hidden_by_user_block = False
    p.location = None
    p.phone = None
    return p


def make_pref(id=1, workplace_id=1, user_id=1):
    from app.models.recommendation_preference import RecommendationPreference
    pref = RecommendationPreference()
    pref.id = id
    pref.workplace_id = workplace_id
    pref.user_id = user_id
    pref.budget = 1500.0
    pref.preferred_transportation = "driving"
    pref.max_distance_km = 10.0
    return pref


# ── Fixtures compartidos ──────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """DB mockeada que no conecta a ninguna base de datos real."""
    db = MagicMock()

    def _refresh(obj):
        # Simula que el DB asigna el id autogenerado después del INSERT
        if getattr(obj, "id", None) is None:
            obj.id = 1
        # is_active tiene default=True en el modelo pero SQLAlchemy no lo aplica
        # hasta el flush real → lo ponemos aquí para que Pydantic pueda serializar
        if hasattr(obj, "is_active") and obj.is_active is None:
            obj.is_active = True

    db.refresh.side_effect = _refresh
    return db


@pytest.fixture
def mock_user():
    return make_user()


@pytest.fixture
def mock_admin():
    return make_user(id=99, email="admin@test.com", role="admin")


@pytest.fixture(scope="session")
def test_app():
    """
    App FastAPI de prueba que incluye todos los routers SIN ejecutar
    el bloque de startup de main.py (que conecta a la DB real).
    """
    from app.api import auth, workplaces, properties, recommendation_preferences
    from app.api import admin, geocode, recommend

    _app = FastAPI(title="Test App")
    _app.include_router(auth.router)
    _app.include_router(workplaces.router)
    _app.include_router(properties.router)
    _app.include_router(recommendation_preferences.router)
    _app.include_router(admin.router)
    _app.include_router(geocode.router)
    _app.include_router(recommend.router)
    return _app


@pytest.fixture
def client(test_app, mock_db, mock_user):
    """TestClient con usuario normal autenticado."""
    from app.core.database import get_db
    from app.core.security import get_current_user, get_current_user_optional

    test_app.dependency_overrides[get_db] = lambda: mock_db
    test_app.dependency_overrides[get_current_user] = lambda: mock_user
    test_app.dependency_overrides[get_current_user_optional] = lambda: mock_user

    with TestClient(test_app, raise_server_exceptions=False) as c:
        yield c

    test_app.dependency_overrides.clear()


@pytest.fixture
def anon_client(test_app, mock_db):
    """TestClient sin autenticación (usuario opcional = None)."""
    from app.core.database import get_db
    from app.core.security import get_current_user_optional

    test_app.dependency_overrides[get_db] = lambda: mock_db
    test_app.dependency_overrides[get_current_user_optional] = lambda: None

    with TestClient(test_app, raise_server_exceptions=False) as c:
        yield c

    test_app.dependency_overrides.clear()


@pytest.fixture
def admin_client(test_app, mock_db, mock_admin):
    """TestClient con rol admin."""
    from app.core.database import get_db
    from app.core.security import get_current_user, get_current_user_optional, get_current_admin

    test_app.dependency_overrides[get_db] = lambda: mock_db
    test_app.dependency_overrides[get_current_user] = lambda: mock_admin
    test_app.dependency_overrides[get_current_user_optional] = lambda: mock_admin
    test_app.dependency_overrides[get_current_admin] = lambda: mock_admin

    with TestClient(test_app, raise_server_exceptions=False) as c:
        yield c

    test_app.dependency_overrides.clear()


# ── Fixture para limpiar caches de geocode ────────────────────────────────────

@pytest.fixture(autouse=True)
def limpiar_caches():
    import app.api.geocode as geocode_module
    geocode_module._search_cache.clear()
    geocode_module._reverse_cache.clear()
    yield
    geocode_module._search_cache.clear()
    geocode_module._reverse_cache.clear()
