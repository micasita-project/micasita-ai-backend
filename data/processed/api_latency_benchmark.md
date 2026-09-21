# API latency benchmark

Generado por `scripts/benchmark_api_latency.py` contra el backend corriendo localmente (`uvicorn app.main:app`), base de datos sembrada con el dataset real (1,356 propiedades). 30 requests por endpoint, tras 2 de warm-up descartadas.

## `POST /recommend/guest`

| Métrica | Valor |
|---|---|
| N | 30 |
| Media | 0.208 s |
| Mediana | 0.184 s |
| P95 | 0.317 s |
| Min / Max | 0.145 s / 0.487 s |
| Desv. estándar | 0.069 s |

## `GET /route`

| Métrica | Valor |
|---|---|
| N | 30 |
| Media | 0.005 s |
| Mediana | 0.005 s |
| P95 | 0.007 s |
| Min / Max | 0.004 s / 0.011 s |
| Desv. estándar | 0.001 s |

