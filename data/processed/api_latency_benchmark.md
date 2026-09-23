# API latency benchmark

Generado por `scripts/benchmark_api_latency.py` contra el backend corriendo localmente (`uvicorn app.main:app`), base de datos sembrada con el dataset real (1,356 propiedades). 30 requests por endpoint, tras 2 de warm-up descartadas.

## `POST /recommend/guest`

| Métrica | Valor |
|---|---|
| N | 30 |
| Media | 0.225 s |
| Mediana | 0.227 s |
| P95 | 0.301 s |
| Min / Max | 0.152 s / 0.306 s |
| Desv. estándar | 0.040 s |

## `POST /recommend/workplaces/{id}/generate`

| Métrica | Valor |
|---|---|
| N | 30 |
| Media | 0.470 s |
| Mediana | 0.457 s |
| P95 | 0.561 s |
| Min / Max | 0.405 s / 0.563 s |
| Desv. estándar | 0.048 s |

## `GET /route`

| Métrica | Valor |
|---|---|
| N | 30 |
| Media | 0.007 s |
| Mediana | 0.007 s |
| P95 | 0.007 s |
| Min / Max | 0.006 s / 0.008 s |
| Desv. estándar | 0.000 s |

