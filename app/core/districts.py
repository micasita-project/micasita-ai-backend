"""
Normalización de distritos de Lima Metropolitana.

Problema que resuelve: el campo `district` que llega del portal inmobiliario no
contiene distritos, contiene lo que el anunciante escribió. En el catálogo de
1 419 viviendas hay **149 valores distintos**, mezclando:

  - distritos reales      -> "Miraflores, Lima"
  - urbanizaciones        -> "Risso, Lince" · "Corpac, San Isidro" · "Armendariz"
  - la ciudad a secas     -> "Lima"  (1 067 de 1 419 registros)
  - alias y variantes     -> "Surco" · "Magdalena" · "Lima Cercado"

Eso rompe dos cosas: el filtro por distrito de la app (buscar "Surco" no encuentra
lo archivado como "Chacarilla") y cualquier uso del distrito como variable del
modelo, porque una categoría vista en entrenamiento puede no existir en inferencia.

Estrategia, en orden de confianza:

  1. **El geocodificador manda.** TomTom devuelve la dirección estructurada, y su
     campo `municipalitySubdivision` es el distrito oficial del punto. Es la fuente
     más fiable porque viene de la coordenada, no del texto del anuncio.
  2. **Si no hay geocodificador**, se parsea el texto: se prueba cada componente
     separado por comas contra la lista canónica, sin acentos ni mayúsculas.
  3. **Si nada coincide**, se devuelve None y el llamador conserva el texto original
     en `district_raw`. Nunca se inventa un distrito.
"""

import unicodedata

# Los 43 distritos de la provincia de Lima y los 7 del Callao.
DISTRITOS_LIMA = [
    "Ancón", "Ate", "Barranco", "Breña", "Carabayllo", "Chaclacayo", "Chorrillos",
    "Cieneguilla", "Comas", "El Agustino", "Independencia", "Jesús María",
    "La Molina", "La Victoria", "Lima", "Lince", "Los Olivos", "Lurigancho",
    "Lurín", "Magdalena del Mar", "Miraflores", "Pachacámac", "Pucusana",
    "Pueblo Libre", "Puente Piedra", "Punta Hermosa", "Punta Negra", "Rímac",
    "San Bartolo", "San Borja", "San Isidro", "San Juan de Lurigancho",
    "San Juan de Miraflores", "San Luis", "San Martín de Porres", "San Miguel",
    "Santa Anita", "Santa María del Mar", "Santa Rosa", "Santiago de Surco",
    "Surquillo", "Villa El Salvador", "Villa María del Triunfo",
]

DISTRITOS_CALLAO = [
    "Bellavista", "Callao", "Carmen de la Legua Reynoso", "La Perla", "La Punta",
    "Mi Perú", "Ventanilla",
]

DISTRITOS = DISTRITOS_LIMA + DISTRITOS_CALLAO


def _clave(texto: str) -> str:
    """Minúsculas sin acentos ni puntuación, para comparar sin sorpresas."""
    t = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.replace(".", " ").replace("-", " ").split())


# Índice canónico y alias frecuentes del portal.
_INDICE = {_clave(d): d for d in DISTRITOS}
_ALIAS = {
    "surco": "Santiago de Surco",
    "magdalena": "Magdalena del Mar",
    "magdalena vieja": "Pueblo Libre",
    "lima cercado": "Lima",
    "cercado de lima": "Lima",
    "cercado": "Lima",
    "chosica": "Lurigancho",
    "lurigancho chosica": "Lurigancho",
    "jesus maria": "Jesús María",
    "brena": "Breña",
    "rimac": "Rímac",
    "san martin de porres": "San Martín de Porres",
    "smp": "San Martín de Porres",
    "sjl": "San Juan de Lurigancho",
    "sjm": "San Juan de Miraflores",
    "vmt": "Villa María del Triunfo",
    "ves": "Villa El Salvador",
    "ate vitarte": "Ate",
    "vitarte": "Ate",
    "villa maria del triunfo": "Villa María del Triunfo",
    "villa el salvador": "Villa El Salvador",
    "carmen de la legua": "Carmen de la Legua Reynoso",
    "mi peru": "Mi Perú",
}
_INDICE.update(_ALIAS)


def normalizar_distrito(texto: str) -> str | None:
    """
    Devuelve el distrito canónico o None si no se reconoce.

    Prueba el texto completo y luego cada componente separado por comas, de
    derecha a izquierda: en "Risso, Lince" el distrito es el último componente,
    y en "Miraflores, Lima" hay que quedarse con Miraflores y no con Lima.
    """
    if not texto:
        return None

    directo = _INDICE.get(_clave(texto))
    if directo:
        return directo

    partes = [p for p in (texto.split(",")) if p.strip()]

    # De derecha a izquierda, pero saltando "Lima" mientras haya algo más
    # específico: "Miraflores, Lima" debe dar Miraflores.
    candidatos = []
    for p in reversed(partes):
        d = _INDICE.get(_clave(p))
        if d:
            candidatos.append(d)
    if candidatos:
        especificos = [c for c in candidatos if c != "Lima"]
        return especificos[0] if especificos else "Lima"

    return None


def distrito_desde_tomtom(address: dict) -> str | None:
    """
    Extrae el distrito de la dirección estructurada que devuelve TomTom.

    Solo se lee `municipalitySubdivision`, que es el nivel de distrito, y se
    valida contra la lista canónica para no aceptar urbanizaciones que TomTom
    a veces pone ahí.

    NO se cae a `municipality`: en Lima Metropolitana ese campo vale "Lima", que
    es la ciudad y no el distrito. Usarlo producía falsos "Lima" que hacían
    fallar la validación cruzada y descartaban coordenadas correctas; pasó con
    un aviso de Lince cuya coordenada era buena.

    Devolver None significa "no sé", y el llamador lo trata como aceptable.
    """
    if not address:
        return None
    valor = address.get("municipalitySubdivision")
    if not valor:
        return None
    # TomTom puede devolver varios niveles separados por coma
    return normalizar_distrito(valor)


def distrito_desde_nominatim(address: dict) -> str | None:
    """
    Extrae el distrito de la dirección estructurada de Nominatim
    (requiere `addressdetails=1` en la consulta).

    En Lima el distrito aparece normalmente en `city_district` o `suburb`.
    """
    if not address:
        return None
    for campo in ("city_district", "suburb", "town", "municipality",
                  "county", "city"):
        valor = address.get(campo)
        if not valor:
            continue
        d = normalizar_distrito(valor)
        if d:
            return d
    return None


def resumen(valores) -> dict:
    """Cuántos valores crudos se resuelven y cuántos no. Útil para auditar."""
    ok, fallan = {}, {}
    for v in valores:
        d = normalizar_distrito(v)
        if d:
            ok[d] = ok.get(d, 0) + 1
        else:
            fallan[v] = fallan.get(v, 0) + 1
    return {"resueltos": ok, "sin_resolver": fallan}
