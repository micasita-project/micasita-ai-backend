"""
Benchmark de latencia real contra la API corriendo localmente. Mide el tiempo
de respuesta de los endpoints que más carga imponen: la generación de
recomendaciones sin cuenta (POST /recommend/guest), la generación con cuenta
autenticada (POST /recommend/workplaces/{id}/generate) y el ruteo puntual
(GET /route, un solo trayecto).

/recommend/guest y /recommend/workplaces/{id}/generate llaman a la misma
función interna (generar_recomendacion() en recommendation_service.py) — el
pipeline pesado (filtrar candidatas, llamar OSRM en lote, corregir con
XGBoost) es idéntico. La diferencia de /generate es una consulta a BD para
traer workplace/preferencias en vez de recibirlos en el body, y un INSERT al
historial al final. Se miden ambos por separado para cuantificar esa
sobrecarga extra frente al costo dominante de OSRM+XGBoost.

Requiere que el backend ya esté corriendo (uvicorn app.main:app) y la base de
datos sembrada. No inicia el servidor por sí mismo, para no mezclar el tiempo
de arranque en frío con la latencia de request real.

Para /generate se necesita un workplace + recommendation_preference reales
con los mismos parámetros que RECOMMEND_PAYLOAD (mismo budget/modo/distancia,
para que ambos endpoints filtren el mismo conjunto de candidatas) y un JWT
válido para el usuario dueño de ese workplace:

    INSERT INTO workplaces (user_id, work_address, work_lat, work_lon)
    VALUES (<user_id>, '<fixture>', -12.0931, -77.0010);
    INSERT INTO recommendation_preferences
      (user_id, workplace_id, budget, preferred_transportation, max_distance_km)
    VALUES (<user_id>, <workplace_id>, 3000, 'driving', 10.0);

    python -c "from app.core.security import create_access_token; \
        from datetime import timedelta; \
        print(create_access_token({'sub': '<user_email>'}, timedelta(hours=2)))"

Uso:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 &
    AUTH_WORKPLACE_ID=<id> AUTH_TOKEN=<jwt> python scripts/benchmark_api_latency.py
"""

import os
import statistics as st
import time

import httpx

BASE_URL = "http://127.0.0.1:8000"
N_REQUESTS = 30
WARMUP = 2  # descartadas del cálculo, solo para no medir el primer conexionado en frío

AUTH_WORKPLACE_ID = os.environ.get("AUTH_WORKPLACE_ID")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")

RECOMMEND_PAYLOAD = {
    "work_lat": -12.0931, "work_lon": -77.0010,
    "budget": 3000, "preferred_transportation": "driving",
    "max_distance_km": 10.0,
}

ROUTE_PARAMS = {
    "origin_lat": -12.0931, "origin_lon": -77.0010,
    "dest_lat": -12.0464, "dest_lon": -77.0428,
    "mode": "driving",
}


def medir(nombre: str, fn) -> list[float]:
    tiempos = []
    for i in range(WARMUP + N_REQUESTS):
        t0 = time.perf_counter()
        r = fn()
        elapsed = time.perf_counter() - t0
        r.raise_for_status()
        if i >= WARMUP:
            tiempos.append(elapsed)
    return tiempos


def reportar(nombre: str, tiempos: list[float]):
    tiempos_ordenados = sorted(tiempos)
    p95_idx = int(len(tiempos_ordenados) * 0.95)
    p95 = tiempos_ordenados[min(p95_idx, len(tiempos_ordenados) - 1)]
    print(f"\n{nombre} (N={len(tiempos)} requests, tras {WARMUP} de warm-up descartadas)")
    print(f"  media   : {st.mean(tiempos):.3f} s")
    print(f"  mediana : {st.median(tiempos):.3f} s")
    print(f"  p95     : {p95:.3f} s")
    print(f"  min/max : {min(tiempos):.3f} s / {max(tiempos):.3f} s")
    print(f"  stdev   : {st.stdev(tiempos):.3f} s")
    return {
        "n": len(tiempos), "media": st.mean(tiempos), "mediana": st.median(tiempos),
        "p95": p95, "min": min(tiempos), "max": max(tiempos), "stdev": st.stdev(tiempos),
    }


def main():
    with httpx.Client(timeout=30.0) as client:
        resultados = {}

        t = medir("recommend_guest", lambda: client.post(f"{BASE_URL}/recommend/guest", json=RECOMMEND_PAYLOAD))
        resultados["POST /recommend/guest"] = reportar("POST /recommend/guest", t)

        if AUTH_WORKPLACE_ID and AUTH_TOKEN:
            headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
            url = f"{BASE_URL}/recommend/workplaces/{AUTH_WORKPLACE_ID}/generate"
            t = medir("recommend_generate_auth", lambda: client.post(url, headers=headers))
            resultados["POST /recommend/workplaces/{id}/generate"] = reportar(
                "POST /recommend/workplaces/{id}/generate", t
            )
        else:
            print("\n(Omitiendo /recommend/workplaces/{id}/generate: faltan AUTH_WORKPLACE_ID/AUTH_TOKEN)")

        t = medir("route", lambda: client.get(f"{BASE_URL}/route", params=ROUTE_PARAMS))
        resultados["GET /route"] = reportar("GET /route", t)

    out_path = "data/processed/api_latency_benchmark.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# API latency benchmark\n\n")
        f.write(f"Generado por `scripts/benchmark_api_latency.py` contra el backend "
                f"corriendo localmente (`uvicorn app.main:app`), base de datos sembrada "
                f"con el dataset real (1,356 propiedades). {N_REQUESTS} requests por "
                f"endpoint, tras {WARMUP} de warm-up descartadas.\n\n")
        for nombre, r in resultados.items():
            f.write(f"## `{nombre}`\n\n")
            f.write(f"| Métrica | Valor |\n|---|---|\n")
            f.write(f"| N | {r['n']} |\n")
            f.write(f"| Media | {r['media']:.3f} s |\n")
            f.write(f"| Mediana | {r['mediana']:.3f} s |\n")
            f.write(f"| P95 | {r['p95']:.3f} s |\n")
            f.write(f"| Min / Max | {r['min']:.3f} s / {r['max']:.3f} s |\n")
            f.write(f"| Desv. estándar | {r['stdev']:.3f} s |\n\n")
    print(f"\nGuardado: {out_path}")


if __name__ == "__main__":
    main()
