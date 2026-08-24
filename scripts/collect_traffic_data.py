"""
Recolecta la etiqueta supervisada del modelo: el tiempo de viaje REAL con tráfico.

Por cada trayecto (centro de trabajo -> vivienda, modo, franja horaria) consulta
dos servicios y guarda ambas respuestas en la misma fila:

  - OSRM   -> tiempo de flujo libre + distancia de ruta   (la ENTRADA del modelo)
  - TomTom -> tiempo con tráfico para una hora de salida   (la ETIQUETA del modelo)

TomTom se usa una sola vez, aquí, para construir el dataset. En producción no se
llama: el modelo aprende la corrección y la aplica sobre OSRM, que es gratuito y
autohospedado.

Salida: data/processed/travel_time_dataset.csv (se escribe incrementalmente y el
script es reanudable: al volver a correr, omite los trayectos ya recolectados).

Uso:
    # 1. Ver el plan sin gastar cuota
    PYTHONPATH=. python scripts/collect_traffic_data.py --dry-run

    # 2. Recolectar respetando la cuota diaria gratuita
    PYTHONPATH=. python scripts/collect_traffic_data.py --max-requests 2300

Requiere TOMTOM_API_KEY en el entorno o en .env
"""

import argparse
import csv
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from math import radians, sin, cos, sqrt, atan2
from urllib import error, parse, request

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #

HOUSING_PATH = "data/raw/housing.json"
OUTPUT_PATH = "data/processed/travel_time_dataset.csv"

TOMTOM_URL = "https://api.tomtom.com/routing/1/calculateRoute/{loc}/json"

# OSRM: una instancia por perfil, cada una con su propio grafo.
#
# El path dice /driving en los tres casos a propósito: osrm-routed IGNORA ese
# segmento de la URL. El perfil lo define el grafo con el que se construyó la
# instancia (car.lua / bicycle.lua / foot.lua), no la ruta HTTP.
#
# Comprobado sobre estas mismas instancias, trayecto Miraflores -> San Isidro:
#   mismo puerto 5003, paths /driving /bike /foot /cycling /walking  -> los cinco
#     devuelven 3.189 km y 6.29 min (idénticos: el path no hace nada)
#   mismo path /driving, puertos distintos -> 30.4 km/h (car), 14.2 km/h (bike),
#     5.0 km/h (foot)  (el grafo sí manda)
#
# Es el mismo criterio que ya usan dataset_builder.py y recommendation_service.py.
OSRM_BASE_URLS = {
    "driving": os.getenv("OSRM_DRIVING_URL", "http://localhost:5003/route/v1/driving"),
    "cycling": os.getenv("OSRM_CYCLING_URL", "http://localhost:5001/route/v1/driving"),
    "walking": os.getenv("OSRM_WALKING_URL", "http://localhost:5002/route/v1/driving"),
}

# Precisión con la que se redondean las coordenadas para identificar un trayecto.
# 4 decimales ~ 11 m, por debajo del error con que OSRM engancha un punto a la vía
# más cercana. Redondear cumple dos funciones:
#   1. Une viviendas que comparten edificio o centroide de geocodificación, así no
#      se paga cuota de TomTom dos veces por el mismo trayecto (hoy 70 de 392
#      viviendas comparten coordenada exacta con otra).
#   2. Hace que el dataset sea INDEPENDIENTE de los IDs del catálogo. Si se vuelve
#      a correr el scraper y los IDs cambian, lo ya recolectado sigue sirviendo:
#      la etiqueta depende del trayecto, no de qué aviso lo originó.
PRECISION_COORD = 4

# Modo interno -> travelMode de TomTom
TOMTOM_MODE = {"driving": "car", "cycling": "bicycle", "walking": "pedestrian"}

# Centro histórico de Lima: referencia para el sentido del viaje.
LIMA_CENTER = (-12.0464, -77.0428)

# Recuadro de Lima Metropolitana. Copiado de app/core/geo.py para que el dataset
# cubra exactamente la zona que la aplicación acepta.
LIMA_BBOX = {"lat_min": -12.55, "lat_max": -11.70, "lon_min": -77.20, "lon_max": -76.65}

# Franjas horarias. Lima es UTC-05:00 todo el año.
LIMA_UTC_OFFSET = "-05:00"
FRANJAS = {
    "punta_manana": 7,   # entrada al trabajo
    "valle": 13,         # mediodía, tráfico bajo
    "punta_tarde": 18,   # salida del trabajo
}

# Polos de empleo de Lima, organizados por tipo de hub (corporativo, comercial,
# industrial/logístico) en vez de solo por distrito. Reemplaza a la lista anterior
# de 11 centros sueltos.
#
# Los 10 puntos están validados contra la red vial real con
# `scripts/validar_coordenadas.py` (servicio /nearest de OSRM): 9 enganchan a
# menos de 35 m de una vía mapeada; W09 Callao da 176 m (zona portuaria/industrial,
# esperable que tenga menos vías mapeadas que el centro — igual "aceptable", no
# cae fuera de la red). No hace falta precisión de dirección exacta, porque OSRM
# engancha el punto a la calle más cercana de todos modos; lo que importa es caer
# en la zona urbana correcta.
#
# Para usar otros centros: --workplaces archivo.json, y validarlos con
#     PYTHONPATH=. python scripts/validar_coordenadas.py

CENTROS_TRABAJO = [
    # Hub corporativo (oficinas)
    {"id": "W01", "hub": "Corporativo", "nombre": "San Isidro Financiero",
     "lat": -12.0961, "lon": -77.0264},
    {"id": "W02", "hub": "Corporativo", "nombre": "Miraflores Centro",
     "lat": -12.1211, "lon": -77.0300},
    {"id": "W03", "hub": "Corporativo", "nombre": "Surco (El Derby / Manuel Olguín)",
     "lat": -12.0976, "lon": -76.9728},
    {"id": "W04", "hub": "Corporativo", "nombre": "Magdalena (hub Javier Prado Oeste)",
     "lat": -12.0940, "lon": -77.0573},

    # Hub comercial y administrativo
    {"id": "W05", "hub": "Comercial", "nombre": "Cercado de Lima (centro histórico)",
     "lat": -12.0458, "lon": -77.0305},
    {"id": "W06", "hub": "Comercial", "nombre": "La Victoria (emporio Gamarra)",
     "lat": -12.0704, "lon": -77.0125},
    {"id": "W07", "hub": "Comercial/Norte", "nombre": "Independencia / Los Olivos (MegaPlaza)",
     "lat": -11.9951, "lon": -77.0617},

    # Hub industrial y logístico (carga pesada / operarios)
    {"id": "W08", "hub": "Industrial", "nombre": "Ate / Santa Anita (Carretera Central)",
     "lat": -12.0430, "lon": -76.9500},
    {"id": "W09", "hub": "Industrial/Puerto", "nombre": "Callao (eje Av. Argentina / puerto)",
     "lat": -12.0485, "lon": -77.1015},
    {"id": "W10", "hub": "Industrial", "nombre": "Villa El Salvador (parque industrial)",
     "lat": -12.1951, "lon": -76.9357},
]

CAMPOS = [
    "pair_key",
    # trayecto
    "workplace_id", "workplace_nombre", "work_lat", "work_lon",
    "property_id", "prop_ids", "prop_lat", "prop_lon", "prop_district",
    "modo", "franja", "depart_at", "dia_semana", "hora",
    # entrada del modelo: OSRM (flujo libre)
    "osrm_dist_km", "osrm_min", "osrm_status",
    # contexto geográfico derivado
    "work_dist_centro_km", "prop_dist_centro_km", "hacia_el_centro",
    # etiqueta: TomTom con tráfico
    "tt_dist_km", "tt_min", "tt_sin_trafico_min", "tt_historico_min",
    "tt_demora_min", "tt_status",
]


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def cargar_env():
    """Lee .env sin depender de python-dotenv, que no está en requirements.txt."""
    if not os.path.exists(".env"):
        return
    with open(".env", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            os.environ.setdefault(clave.strip(), valor.strip())


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def dentro_de_lima(lat, lon):
    return (LIMA_BBOX["lat_min"] <= lat <= LIMA_BBOX["lat_max"]
            and LIMA_BBOX["lon_min"] <= lon <= LIMA_BBOX["lon_max"])


def proximo_dia_habil(hora, dia_objetivo=1, dias_minimos=3, fecha_ref=None):
    """
    Devuelve un datetime futuro para `departAt`.

    TomTom usa patrones históricos de tráfico cuando la salida está en el futuro,
    así que se obtiene el tiempo típico de ese día y hora —reproducible— en vez
    del tráfico puntual del momento de la recolección.

    dia_objetivo: 0=lunes, 1=martes (por defecto, día laboral representativo).
    fecha_ref:    fija la fecha (YYYY-MM-DD) para que todo el dataset use la misma
                  semana de referencia aunque la recolección tome varios días.
    """
    if fecha_ref:
        d = datetime.strptime(fecha_ref, "%Y-%m-%d")
    else:
        d = datetime.now() + timedelta(days=dias_minimos)
        while d.weekday() != dia_objetivo:
            d += timedelta(days=1)
    return d.replace(hour=hora, minute=0, second=0, microsecond=0)


# --------------------------------------------------------------------------- #
# Clientes HTTP
# --------------------------------------------------------------------------- #

def consultar_osrm(lat1, lon1, lat2, lon2, modo, timeout=15):
    """Tiempo de flujo libre y distancia de ruta. Devuelve (dist_km, min, status)."""
    base = OSRM_BASE_URLS.get(modo, OSRM_BASE_URLS["driving"])
    url = f"{base}/{lon1},{lat1};{lon2},{lat2}?overview=false&steps=false"
    try:
        with request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") != "Ok" or not data.get("routes"):
            return None, None, f"osrm_sin_ruta:{data.get('code')}"
        r = data["routes"][0]
        return round(r["distance"] / 1000, 3), round(r["duration"] / 60, 2), "ok"
    except error.HTTPError as e:
        return None, None, f"osrm_http_{e.code}"
    except Exception as e:
        return None, None, f"osrm_error:{type(e).__name__}"


def consultar_tomtom(api_key, lat1, lon1, lat2, lon2, modo, depart_at, timeout=20):
    """
    Tiempo con tráfico para una hora de salida dada.

    computeTravelTimeFor=all hace que el resumen incluya además el tiempo SIN
    tráfico y el histórico. Eso permite separar dos efectos en el análisis:
      - OSRM vs tt_sin_trafico  -> diferencias de cartografía entre motores
      - tt_sin_trafico vs tt    -> el efecto puro de la congestión
    """
    loc = f"{lat1},{lon1}:{lat2},{lon2}"
    params = {
        "key": api_key,
        "travelMode": TOMTOM_MODE[modo],
        "routeType": "fastest",
        "traffic": "true",
        "computeTravelTimeFor": "all",
        "departAt": depart_at,
    }
    url = TOMTOM_URL.format(loc=parse.quote(loc)) + "?" + parse.urlencode(params)
    try:
        with request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rutas = data.get("routes") or []
        if not rutas:
            return {}, "tt_sin_ruta"
        s = rutas[0]["summary"]

        def minutos(clave):
            v = s.get(clave)
            return round(v / 60, 2) if v is not None else None

        return {
            "tt_dist_km": round(s["lengthInMeters"] / 1000, 3),
            "tt_min": minutos("travelTimeInSeconds"),
            "tt_sin_trafico_min": minutos("noTrafficTravelTimeInSeconds"),
            "tt_historico_min": minutos("historicTrafficTravelTimeInSeconds"),
            "tt_demora_min": minutos("trafficDelayInSeconds"),
        }, "ok"
    except error.HTTPError as e:
        cuerpo = ""
        try:
            cuerpo = e.read().decode("utf-8", "ignore")[:180]
        except Exception:
            pass
        return {}, f"tt_http_{e.code}:{cuerpo}"
    except Exception as e:
        return {}, f"tt_error:{type(e).__name__}"


# --------------------------------------------------------------------------- #
# Construcción del plan de trabajo
# --------------------------------------------------------------------------- #

def snap(x):
    """Redondea una coordenada a la rejilla que identifica un trayecto."""
    return round(float(x), PRECISION_COORD)


def cargar_viviendas(path, muestra, semilla):
    """
    Devuelve UBICACIONES distintas, no avisos.

    Varias viviendas pueden compartir coordenada (mismo edificio, o centroide de
    geocodificación). Para el tiempo de viaje son el mismo punto, así que se
    agrupan y se consulta una sola vez. Se conservan todos los IDs del grupo en
    `ids` para poder volver a unir con el catálogo.
    """
    with open(path, encoding="utf-8") as f:
        crudas = json.load(f)

    grupos, descartadas = {}, 0
    for v in crudas:
        lat, lon = v.get("latitude"), v.get("longitude")
        if lat is None or lon is None:
            descartadas += 1
            continue
        lat, lon = snap(lat), snap(lon)
        if not dentro_de_lima(lat, lon):
            descartadas += 1
            continue
        g = grupos.setdefault((lat, lon), {
            "lat": lat, "lon": lon, "ids": [], "district": v.get("district") or "",
        })
        g["ids"].append(str(v["id"]))

    if descartadas:
        print(f"  aviso: {descartadas} viviendas descartadas por coordenadas "
              f"ausentes o fuera del recuadro de Lima")

    ubicaciones = list(grupos.values())
    total_avisos = sum(len(u["ids"]) for u in ubicaciones)
    ahorro = total_avisos - len(ubicaciones)
    if ahorro:
        print(f"  {total_avisos} avisos -> {len(ubicaciones)} ubicaciones distintas "
              f"({ahorro} trayectos duplicados que no se pagan)")

    # Muestreo determinista sobre las ubicaciones ya ordenadas, para que ampliar
    # el catálogo no reordene lo anterior.
    ubicaciones.sort(key=lambda u: (u["lat"], u["lon"]))
    if muestra and muestra < len(ubicaciones):
        random.Random(semilla).shuffle(ubicaciones)
        ubicaciones = ubicaciones[:muestra]
    return ubicaciones


def construir_plan(ubicaciones, centros, modos, franjas, fecha_ref=None):
    """
    Una tarea por (origen, destino, modo, franja).

    `pair_key` se arma con las COORDENADAS redondeadas, no con los IDs del
    catálogo: así el archivo de salida sigue siendo válido cuando se vuelva a
    correr el scraper y los IDs cambien.
    """
    horas = {f: proximo_dia_habil(FRANJAS[f], fecha_ref=fecha_ref)
             .strftime(f"%Y-%m-%dT%H:%M:%S{LIMA_UTC_OFFSET}") for f in franjas}

    plan = []
    for c in centros:
        w_lat, w_lon = snap(c["lat"]), snap(c["lon"])
        w_centro = haversine(w_lat, w_lon, *LIMA_CENTER)
        for u in ubicaciones:
            p_centro = haversine(u["lat"], u["lon"], *LIMA_CENTER)
            for modo in modos:
                for f in franjas:
                    plan.append({
                        "pair_key": f"{w_lat},{w_lon}|{u['lat']},{u['lon']}|{modo}|{f}",
                        "workplace_id": c["id"], "workplace_nombre": c["nombre"],
                        "work_lat": w_lat, "work_lon": w_lon,
                        # representativo + todos los avisos en esa ubicación
                        "property_id": u["ids"][0],
                        "prop_ids": ";".join(u["ids"]),
                        "prop_lat": u["lat"], "prop_lon": u["lon"],
                        "prop_district": u["district"],
                        "modo": modo, "franja": f, "depart_at": horas[f],
                        "dia_semana": datetime.strptime(horas[f][:19], "%Y-%m-%dT%H:%M:%S").weekday(),
                        "hora": FRANJAS[f],
                        "work_dist_centro_km": round(w_centro, 3),
                        "prop_dist_centro_km": round(p_centro, 3),
                        # 1 si el trabajo está más cerca del centro que la vivienda,
                        # es decir el viaje de ida va hacia el centro.
                        "hacia_el_centro": int(w_centro < p_centro),
                    })
    return plan


def claves_ya_hechas(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {fila["pair_key"] for fila in csv.DictReader(f) if fila.get("pair_key")}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="muestra el plan y la cuota estimada sin llamar a ninguna API")
    ap.add_argument("--max-requests", type=int, default=2300,
                    help="tope de llamadas a TomTom en esta corrida (capa gratuita: 2500/día)")
    ap.add_argument("--properties", type=int, default=120,
                    help="cuántas UBICACIONES muestrear del catálogo (0 = todas)")
    ap.add_argument("--housing", default=HOUSING_PATH,
                    help="catálogo de viviendas (cambiarlo tras volver a correr el scraper)")
    ap.add_argument("--depart-date",
                    help="fecha de referencia YYYY-MM-DD para departAt; fíjala para que "
                         "todo el dataset use la misma semana aunque tome varios días")
    ap.add_argument("--modes", default="driving",
                    help="modos separados por coma: driving,cycling,walking")
    ap.add_argument("--franjas", default="punta_manana,valle,punta_tarde")
    ap.add_argument("--workplaces", help="JSON con centros de trabajo propios")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rate", type=float, default=0.22,
                    help="segundos entre llamadas a TomTom (capa gratuita: ~5 req/s)")
    ap.add_argument("--output", default=OUTPUT_PATH)
    args = ap.parse_args()

    cargar_env()

    modos = [m.strip() for m in args.modes.split(",") if m.strip()]
    franjas = [f.strip() for f in args.franjas.split(",") if f.strip()]
    for m in modos:
        if m not in TOMTOM_MODE:
            sys.exit(f"modo desconocido: {m} (usa driving, cycling o walking)")
    for f in franjas:
        if f not in FRANJAS:
            sys.exit(f"franja desconocida: {f} (usa {', '.join(FRANJAS)})")

    centros = CENTROS_TRABAJO
    if args.workplaces:
        with open(args.workplaces, encoding="utf-8") as fh:
            centros = json.load(fh)
    fuera = [c["nombre"] for c in centros if not dentro_de_lima(c["lat"], c["lon"])]
    if fuera:
        sys.exit(f"centros de trabajo fuera del recuadro de Lima: {fuera}")

    print("=" * 74)
    print("RECOLECCIÓN DE TIEMPOS DE VIAJE CON TRÁFICO")
    print("=" * 74)

    viviendas = cargar_viviendas(args.housing, args.properties or None, args.seed)
    plan = construir_plan(viviendas, centros, modos, franjas, args.depart_date)
    hechas = claves_ya_hechas(args.output)
    pendientes = [t for t in plan if t["pair_key"] not in hechas]

    horas_usadas = sorted({t["depart_at"] for t in plan})
    print(f"  catálogo           : {args.housing}")
    print(f"  ubicaciones        : {len(viviendas)}")
    print(f"  centros de trabajo : {len(centros)}")
    print(f"  modos              : {', '.join(modos)}")
    print(f"  franjas            : {', '.join(franjas)}")
    print(f"  horas de salida    : {', '.join(horas_usadas)}")
    print()
    print(f"  trayectos del plan : {len(plan)}")
    print(f"  ya recolectados    : {len(hechas)}")
    print(f"  pendientes         : {len(pendientes)}")
    print(f"  tope de esta corrida: {args.max_requests}")
    a_procesar = min(len(pendientes), args.max_requests)
    print(f"  se procesarán      : {a_procesar}")
    if a_procesar:
        est = a_procesar * (args.rate + 0.35) / 60
        print(f"  duración estimada  : ~{est:.0f} min")
    if len(pendientes) > args.max_requests:
        dias = -(-len(pendientes) // args.max_requests)
        print(f"  faltarán {len(pendientes) - args.max_requests} para otra corrida "
              f"({dias} corridas en total a este ritmo)")

    if args.dry_run:
        print("\n  Comprobando requisitos (sin gastar cuota de TomTom):")
        print(f"    TOMTOM_API_KEY   : {'presente' if os.getenv('TOMTOM_API_KEY') else 'FALTA'}")
        # Una sonda por modo contra OSRM: el dataset no se puede construir sin él,
        # porque su tiempo de flujo libre es la entrada principal del modelo.
        for modo in modos:
            lat1, lon1 = centros[0]["lat"], centros[0]["lon"]
            lat2, lon2 = viviendas[0]["lat"], viviendas[0]["lon"]
            _, mins, status = consultar_osrm(lat1, lon1, lat2, lon2, modo, timeout=4)
            detalle = f"responde ({mins:.1f} min de prueba)" if status == "ok" else f"NO responde -> {status}"
            print(f"    OSRM {modo:<8}    : {detalle}")
            print(f"                       {OSRM_BASE_URLS[modo]}")
        print("\n  --dry-run: no se llamó a ninguna API de pago.")
        print("  Antes de la corrida real: verifica CENTROS_TRABAJO y levanta OSRM.")
        return

    if not a_procesar:
        print("\n  Nada pendiente. Dataset completo.")
        return

    api_key = os.getenv("TOMTOM_API_KEY")
    if not api_key:
        sys.exit("\nFalta TOMTOM_API_KEY en el entorno o en .env\n"
                 "Consíguela gratis en https://developer.tomtom.com/ "
                 "(capa gratuita: 2500 llamadas/día).")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    nuevo = not os.path.exists(args.output)
    fh = open(args.output, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=CAMPOS)
    if nuevo:
        writer.writeheader()

    print("\n" + "-" * 74)
    ok = fallos_tt = fallos_osrm = 0
    t0 = time.time()

    try:
        for i, tarea in enumerate(pendientes[:a_procesar], 1):
            fila = dict(tarea)

            d_km, d_min, osrm_status = consultar_osrm(
                tarea["work_lat"], tarea["work_lon"],
                tarea["prop_lat"], tarea["prop_lon"], tarea["modo"])
            fila.update(osrm_dist_km=d_km, osrm_min=d_min, osrm_status=osrm_status)
            if osrm_status != "ok":
                fallos_osrm += 1

            tt, tt_status = consultar_tomtom(
                api_key,
                tarea["work_lat"], tarea["work_lon"],
                tarea["prop_lat"], tarea["prop_lon"],
                tarea["modo"], tarea["depart_at"])
            fila.update(tt)
            fila["tt_status"] = tt_status
            for c in ("tt_dist_km", "tt_min", "tt_sin_trafico_min",
                      "tt_historico_min", "tt_demora_min"):
                fila.setdefault(c, None)

            if tt_status == "ok":
                ok += 1
            else:
                fallos_tt += 1
                # 403 y 429 casi siempre son cuota agotada: no seguir quemando llamadas.
                if "tt_http_403" in tt_status or "tt_http_429" in tt_status:
                    print(f"\n  Cuota o permisos agotados ({tt_status[:60]}). "
                          f"Deteniendo para no perder llamadas.")
                    writer.writerow(fila)
                    break

            writer.writerow(fila)

            if i % 25 == 0:
                fh.flush()
                vel = i / max(time.time() - t0, 1e-9)
                restan = (a_procesar - i) / max(vel, 1e-9) / 60
                print(f"  {i}/{a_procesar}  ok={ok}  fallos_tt={fallos_tt}  "
                      f"fallos_osrm={fallos_osrm}  ~{restan:.0f} min restantes")

            time.sleep(args.rate)
    except KeyboardInterrupt:
        print("\n  Interrumpido. Lo recolectado queda guardado; volver a correr reanuda.")
    finally:
        fh.close()

    print("-" * 74)
    print(f"  etiquetas obtenidas : {ok}")
    print(f"  fallos TomTom       : {fallos_tt}")
    print(f"  fallos OSRM         : {fallos_osrm}")
    print(f"  archivo             : {args.output}")
    if fallos_osrm == a_procesar and a_procesar:
        print("\n  OSRM falló en todas: revisa que las instancias estén levantadas")
        print(f"  o exporta OSRM_DRIVING_URL. Actual: {OSRM_BASE_URLS['driving']}")


if __name__ == "__main__":
    main()
