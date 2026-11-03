"""
Tests de scripts/seed_db.py: el seed crea solo el admin y las viviendas del JSON.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.property import Property
from app.models.user import User
from app.models.workplace import Workplace
from app.models.recommendation_preference import RecommendationPreference
from scripts import seed_db

HOUSING = [
    {"title": "Depto A", "price": 1200, "latitude": -12.05, "longitude": -77.04, "total_area_sqm": 60},
    {"title": "Depto B", "price": 0, "latitude": -12.06, "longitude": -77.05, "total_area_sqm": 50},
    {"title": "Depto C", "price": 900, "latitude": -12.07, "longitude": -77.06, "total_area_sqm": 40},
]


@pytest.fixture
def seed_env(tmp_path):
    json_path = tmp_path / "housing.json"
    json_path.write_text(json.dumps(HOUSING), encoding="utf-8")
    db = MagicMock()
    db.query.return_value.first.return_value = None
    with patch.object(seed_db, "SessionLocal", return_value=db), \
         patch.object(seed_db, "engine", MagicMock()), \
         patch.object(seed_db, "Base", MagicMock()), \
         patch.object(seed_db, "JSON_PATH", str(json_path)), \
         patch.object(seed_db.settings, "SEED_ADMIN_EMAIL", "admin@prueba.com"), \
         patch.object(seed_db.settings, "SEED_ADMIN_PASSWORD", "Clave-Segura-1"):
        yield db


def _added(db):
    objs = [c.args[0] for c in db.add.call_args_list]
    for c in db.add_all.call_args_list:
        objs.extend(c.args[0])
    return objs


class TestSeedDb:
    def test_crea_un_admin_con_el_correo_configurado(self, seed_env):
        seed_db.seed_database()
        users = [o for o in _added(seed_env) if isinstance(o, User)]
        assert len(users) == 1
        assert users[0].role == "admin"
        assert users[0].email == "admin@prueba.com"

    def test_no_crea_casa_ni_lugar_de_trabajo_ni_preferencias(self, seed_env):
        seed_db.seed_database()
        objs = _added(seed_env)
        assert not any(isinstance(o, (Workplace, RecommendationPreference)) for o in objs)
        admin = next(o for o in objs if isinstance(o, User))
        assert admin.home_lat is None and admin.home_lon is None and admin.home_address is None

    def test_carga_solo_las_viviendas_con_precio(self, seed_env):
        seed_db.seed_database()
        props = [o for o in _added(seed_env) if isinstance(o, Property)]
        assert sorted(p.title for p in props) == ["Depto A", "Depto C"]
        assert all(p.status == "approved" for p in props)

    def test_sin_correo_de_admin_no_crea_nada(self, seed_env):
        with patch.object(seed_db.settings, "SEED_ADMIN_EMAIL", ""):
            seed_db.seed_database()
        seed_env.add.assert_not_called()
        seed_env.add_all.assert_not_called()

    def test_si_ya_hay_usuarios_no_hace_nada(self, seed_env):
        seed_env.query.return_value.first.return_value = User()
        seed_db.seed_database()
        seed_env.add.assert_not_called()
        seed_env.add_all.assert_not_called()
