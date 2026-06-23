"""
Tests de endpoints de propiedades:
  GET    /properties/           (feed público paginado)
  GET    /properties/mine
  GET    /properties/favorites
  GET    /properties/{id}
  POST   /properties/
  PATCH  /properties/{id}
  DELETE /properties/{id}
  POST   /properties/{id}/favorite
  DELETE /properties/{id}/favorite
"""

from tests.conftest import make_property, make_user

PROPERTY_PAYLOAD = {
    "title": "Depto Miraflores",
    "property_type": "Departamento",
    "district": "Miraflores",
    "address": "Av. Larco 456",
    "latitude": -12.046,
    "longitude": -77.042,
    "currency": "PEN",
    "price": 1500.0,
    "total_area_sqm": 80.0,
    "covered_area_sqm": 70.0,
    "bedrooms": 2,
    "bathrooms": 1,
    "parking": 0,
}


# ── GET /properties/ (feed público) ──────────────────────────────────────────

class TestListProperties:
    def _setup_paginated(self, mock_db, items, total=None):
        q = mock_db.query.return_value.filter.return_value.filter.return_value
        q.count.return_value = total if total is not None else len(items)
        q.offset.return_value.limit.return_value.all.return_value = items
        # También cubre el caso sin filtros extra (solo dos .filter encadenados en la query base)
        q2 = mock_db.query.return_value.filter.return_value
        q2.count.return_value = total if total is not None else len(items)
        q2.offset.return_value.limit.return_value.all.return_value = items
        # Sin favoritos para usuario anon
        mock_db.query.return_value.filter.return_value.all.return_value = []

    def test_retorna_lista_paginada(self, anon_client, mock_db):
        props = [make_property(id=i) for i in range(1, 4)]
        self._setup_paginated(mock_db, props, total=3)
        resp = anon_client.get("/properties/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_lista_vacia_cuando_no_hay_propiedades(self, anon_client, mock_db):
        self._setup_paginated(mock_db, [], total=0)
        resp = anon_client.get("/properties/")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ── GET /properties/mine ──────────────────────────────────────────────────────

class TestMyProperties:
    def test_retorna_propiedades_del_usuario(self, client, mock_db):
        props = [make_property(id=1), make_property(id=2)]
        # Primera llamada .all() → propiedades; segunda llamada (populate_favorites) → lista vacía de tuples
        mock_db.query.return_value.filter.return_value.all.side_effect = [props, []]
        resp = client.get("/properties/mine")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ── GET /properties/favorites ─────────────────────────────────────────────────

class TestMyFavorites:
    def test_retorna_favoritos_del_usuario(self, client, mock_db):
        fav_props = [make_property(id=5)]
        mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = fav_props
        resp = client.get("/properties/favorites")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["is_favorite"] is True


# ── GET /properties/{id} ──────────────────────────────────────────────────────

class TestGetProperty:
    def test_retorna_propiedad_existente(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = make_property(id=42)
        resp = client.get("/properties/42")
        assert resp.status_code == 200
        assert resp.json()["id"] == 42

    def test_propiedad_no_encontrada_retorna_404(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.get("/properties/999")
        assert resp.status_code == 404


# ── POST /properties/ ─────────────────────────────────────────────────────────

class TestCreateProperty:
    def test_crea_propiedad_en_estado_pending(self, client, mock_db):
        resp = client.post("/properties/", json=PROPERTY_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["title"] == "Depto Miraflores"


# ── PATCH /properties/{id} ───────────────────────────────────────────────────

class TestUpdateProperty:
    def test_propietario_puede_editar(self, client, mock_db, mock_user):
        prop = make_property(id=1, publisher_id=mock_user.id, status="approved")
        mock_db.query.return_value.filter.return_value.first.return_value = prop
        resp = client.patch("/properties/1", json={"title": "Nuevo título"})
        assert resp.status_code == 200

    def test_edicion_vuelve_a_pending(self, client, mock_db, mock_user):
        prop = make_property(id=1, publisher_id=mock_user.id, status="approved")
        mock_db.query.return_value.filter.return_value.first.return_value = prop
        client.patch("/properties/1", json={"title": "Título actualizado"})
        assert prop.status == "pending"

    def test_propiedad_en_pending_no_se_puede_editar(self, client, mock_db, mock_user):
        prop = make_property(id=1, publisher_id=mock_user.id, status="pending")
        mock_db.query.return_value.filter.return_value.first.return_value = prop
        resp = client.patch("/properties/1", json={"title": "X"})
        assert resp.status_code == 403

    def test_no_propietario_retorna_403(self, client, mock_db, mock_user):
        prop = make_property(id=1, publisher_id=999, status="approved")  # otro dueño
        mock_db.query.return_value.filter.return_value.first.return_value = prop
        resp = client.patch("/properties/1", json={"title": "X"})
        assert resp.status_code == 403

    def test_propiedad_no_encontrada_retorna_404(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.patch("/properties/999", json={"title": "X"})
        assert resp.status_code == 404


# ── DELETE /properties/{id} ───────────────────────────────────────────────────

class TestDeleteProperty:
    def test_propietario_puede_eliminar(self, client, mock_db, mock_user):
        prop = make_property(id=1, publisher_id=mock_user.id)
        mock_db.query.return_value.filter.return_value.first.return_value = prop
        resp = client.delete("/properties/1")
        assert resp.status_code == 204

    def test_no_propietario_retorna_403(self, client, mock_db, mock_user):
        prop = make_property(id=1, publisher_id=999)
        mock_db.query.return_value.filter.return_value.first.return_value = prop
        resp = client.delete("/properties/1")
        assert resp.status_code == 403

    def test_propiedad_no_encontrada_retorna_404(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.delete("/properties/999")
        assert resp.status_code == 404


# ── POST /properties/{id}/favorite ────────────────────────────────────────────

class TestAddFavorite:
    def test_agrega_a_favoritos(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            make_property(id=1),  # propiedad existe
            None,                 # no era favorito aún
        ]
        resp = client.post("/properties/1/favorite")
        assert resp.status_code == 201
        mock_db.add.assert_called_once()

    def test_ya_era_favorito_retorna_201(self, client, mock_db):
        from app.models.favorite import Favorite
        fav = Favorite()
        fav.user_id = 1
        fav.property_id = 1
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            make_property(id=1),  # propiedad existe
            fav,                  # ya era favorito
        ]
        resp = client.post("/properties/1/favorite")
        # El decorator del endpoint siempre usa 201; el mensaje diferencia los casos
        assert resp.status_code == 201
        assert "Ya está" in resp.json()["message"]

    def test_propiedad_no_encontrada_retorna_404(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.post("/properties/999/favorite")
        assert resp.status_code == 404


# ── DELETE /properties/{id}/favorite ─────────────────────────────────────────

class TestRemoveFavorite:
    def test_quita_de_favoritos(self, client, mock_db):
        from app.models.favorite import Favorite
        fav = Favorite()
        mock_db.query.return_value.filter.return_value.first.return_value = fav
        resp = client.delete("/properties/1/favorite")
        assert resp.status_code == 200
        mock_db.delete.assert_called_once_with(fav)

    def test_no_estaba_en_favoritos_retorna_404(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.delete("/properties/1/favorite")
        assert resp.status_code == 404
