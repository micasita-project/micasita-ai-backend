# Bounding box de Lima Metropolitana (incluye Callao y conos norte/sur/este)
_LIMA_LAT_MIN = -12.55
_LIMA_LAT_MAX = -11.70
_LIMA_LON_MIN = -77.20
_LIMA_LON_MAX = -76.65

LIMA_LOCATION_ERROR = (
    "Solo aceptamos ubicaciones dentro de Lima Metropolitana. "
    "El punto seleccionado está fuera de nuestra zona de cobertura."
)


def is_within_lima(lat: float, lon: float) -> bool:
    return (
        _LIMA_LAT_MIN <= lat <= _LIMA_LAT_MAX
        and _LIMA_LON_MIN <= lon <= _LIMA_LON_MAX
    )
