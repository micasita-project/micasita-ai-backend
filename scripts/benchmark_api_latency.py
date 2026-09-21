"""
Benchmark de latencia real contra la API corriendo localmente. Mide el tiempo
de respuesta de los dos endpoints que más carga imponen: la generación de
recomendaciones (POST /recommend/guest, que filtra candidatas, llama a OSRM en
lote y corrige con XGBoost) y el ruteo puntual (GET /route, un solo trayecto).

Requiere que el backend ya esté corriendo (uvicorn app.main:app) y la base de
datos sembrada. No inicia el servidor por sí mismo, para no mezclar el tiempo
de arranque en frío con la latencia de request real.

Uso:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 &
    python scripts/benchmark_api_latency.py
"""

import statistics as st
import time

import httpx

BASE_URL = "http://127.0.0.1:8000"
N_REQUESTS = 30
WARMUP = 2  # descartadas del cálculo, solo para no medir el primer conexionado en frío

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
