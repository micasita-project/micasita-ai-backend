"""
Valida coordenadas contra la red vial real usando el servicio /nearest de OSRM.

Para qué sirve: una coordenada puede estar dentro del recuadro de Lima y aun así
no servir, porque cae en un cerro, en un parque, en el mar o en desierto sin
calles mapeadas. OSRM la engancharía a la vía más cercana —a veces a kilómetros—
y el trayecto resultante no representaría un viaje real.

La distancia de enganche es el diagnóstico:
    <  50 m  ->  el punto está sobre la red vial urbana
   50-200 m  ->  aceptable (interior de manzana, retiro, alameda)
  200-500 m  ->  revisar: zona poco mapeada
   >  500 m  ->  mal: probablemente cerro, playa, desierto o error de digitación

Uso:
    PYTHONPATH=. python scripts/validar_coordenadas.py
    PYTHONPATH=. python scripts/validar_coordenadas.py --archivo data/raw/users.json
"""

import argparse
import json
import os
import sys
from urllib import request

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from collect_traffic_data import (  # noqa: E402
    CENTROS_TRABAJO, OSRM_BASE_URLS, dentro_de_lima,
)

# /nearest vive al mismo nivel que /route en la misma instancia
NEAREST_URL = OSRM_BASE_URLS["driving"].replace("/route/v1/", "/nearest/v1/")


def enganche(lat, lon, timeout=8):
    """Devuelve (metros_hasta_la_via, nombre_de_la_via) o (None, motivo)."""
    url = f"{NEAREST_URL}/{lon},{lat}?number=1"
    try:
        with request.urlopen(url, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
        if d.get("code") != "Ok" or not d.get("waypoints"):
            return None, f"OSRM: {d.get('code')}"
        w = d["waypoints"][0]
        return w["distance"], (w.get("name") or "(vía sin nombre)")
    except Exception as e:
        return None, f"error: {type(e).__name__}"


def veredicto(m):
    if m is None:
        return "SIN DATO"
    if m < 50:
        return "OK"
    if m < 200:
        return "aceptable"
    if m < 500:
        return "revisar"
    return "MAL"


def evaluar(puntos, titulo):
    print("=" * 92)
    print(titulo)
    print("=" * 92)
    print(f"  {'etiqueta':<40} {'lat':>10} {'lon':>10} {'engan.':>8}  {'veredicto':<10} vía")
    problemas = []
    for p in puntos:
        lat, lon = p["lat"], p["lon"]
        if not dentro_de_lima(lat, lon):
            print(f"  {p['nombre'][:39]:<40} {lat:>10.4f} {lon:>10.4f} {'—':>8}  "
                  f"{'FUERA DE LIMA':<10}")
            problemas.append((p["nombre"], "fuera del recuadro de Lima"))
            continue
        m, via = enganche(lat, lon)
        v = veredicto(m)
        ms = f"{m:.0f} m" if m is not None else "—"
        print(f"  {p['nombre'][:39]:<40} {lat:>10.4f} {lon:>10.4f} {ms:>8}  {v:<10} {via[:28]}")
        if v in ("revisar", "MAL", "SIN DATO"):
            problemas.append((p["nombre"], f"{v} ({ms})"))
    print()
    if problemas:
        print(f"  {len(problemas)} punto(s) a revisar:")
        for n, r in problemas:
            print(f"    - {n}: {r}")
    else:
        print("  Todos los puntos caen sobre la red vial mapeada.")
    print()
    return problemas


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archivo", help="JSON de usuarios a validar (además de los centros)")
    ap.add_argument("--solo-archivo", action="store_true",
                    help="omite la validación de CENTROS_TRABAJO")
    args = ap.parse_args()

    print(f"\nUsando OSRM en {NEAREST_URL}\n")
    total = []

    if not args.solo_archivo:
        total += evaluar(
            [{"nombre": f"{c['id']} {c['nombre']}", "lat": c["lat"], "lon": c["lon"]}
             for c in CENTROS_TRABAJO],
            "CENTROS DE TRABAJO del script de recolección",
        )

    if args.archivo:
        with open(args.archivo, encoding="utf-8") as f:
            usuarios = json.load(f)

        trabajo = [{"nombre": f"{u['id']} — trabajo", "lat": u["work_lat"], "lon": u["work_lon"]}
                   for u in usuarios if u.get("work_lat") is not None]
        if trabajo:
            total += evaluar(trabajo, f"TRABAJO de los perfiles en {args.archivo}")

        casa = [{"nombre": f"{u['id']} — vivienda actual", "lat": u["home_lat"], "lon": u["home_lon"]}
                for u in usuarios if u.get("home_lat") is not None]
        if casa:
            total += evaluar(casa, f"VIVIENDA ACTUAL de los perfiles en {args.archivo}")
        else:
            print("  (los perfiles todavía no tienen home_lat / home_lon)\n")

    print("=" * 92)
    print(f"RESUMEN: {len(total)} punto(s) requieren verificación manual")
    print("=" * 92)


if __name__ == "__main__":
    main()
