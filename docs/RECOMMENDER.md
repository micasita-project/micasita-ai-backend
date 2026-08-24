# Motor de Recomendación — MiCasita AI

Este documento explica cómo se recomiendan viviendas hoy: qué parte es un modelo de
Machine Learning entrenado y qué parte es una regla de negocio explícita. Reemplaza
una versión anterior de este documento que describía un modelo circular (XGBoost
entrenado para predecir una fórmula escrita a mano a partir de las mismas variables
que la generaban) — ese modelo y su pipeline (`dataset_builder.py`,
`ml_pipeline/predictor.py`, `xgboost_recommender.json`) ya no existen en el repo.

---

## Visión general

Hay **una sola pieza real de Machine Learning** en el sistema: un modelo XGBoost que
corrige el tiempo de viaje de flujo libre que da OSRM (sin tráfico) al tiempo real
que tomaría el trayecto con tráfico. Todo lo demás — cuánto pesa el precio, la
distancia, el área — es una función de utilidad explícita, sin nada "aprendido".

```
OSRM (tiempo sin tráfico) ──► Modelo XGBoost ──► tiempo corregido ──► calcular_match_score()
                                (entrenado                              (precio + tiempo +
                                 contra TomTom)                          distancia + área)
```

La separación es deliberada: el precio y la distancia se pueden calcular con una
fórmula sin necesidad de "aprenderlos". Lo único que de verdad hacía falta un modelo
para estimar bien es el tiempo con tráfico, porque OSRM por sí solo lo subestima de
forma sistemática y variable según la hora del día.

---

## 1. El modelo: corrección de tiempo de viaje

### Por qué hace falta corregirlo

OSRM calcula el tiempo de flujo libre: cuánto tardaría el trayecto sin ningún otro
vehículo en la vía. En Lima, con tráfico real, el tiempo efectivo es
sistemáticamente mayor, y el factor de corrección varía según la hora (punta de la
mañana, valle, punta de la tarde), el modo de transporte y la geografía del
trayecto. Usar el tiempo de OSRM tal cual distorsiona toda la recomendación, porque
el tiempo de viaje es la variable con más peso en el score.

### El dataset: `scripts/collect_traffic_data.py`

Por cada combinación de (centro de trabajo, vivienda, modo, franja horaria), el
script consulta dos servicios y guarda ambas respuestas en la misma fila:

- **OSRM** (autohospedado, grafo recortado a Lima Metropolitana) → tiempo de flujo
  libre y distancia de ruta. Es la **entrada** del modelo, y es gratis: se puede
  llamar todas las veces que haga falta, en desarrollo y en producción.
- **TomTom** (`calculateRoute`, con tráfico) → tiempo real para una hora de salida
  específica. Es la **etiqueta** del modelo. Se usa **una sola vez**, aquí, para
  construir el dataset — nunca en producción, porque tiene cuota limitada y de pago.

El resultado es `data/processed/travel_time_dataset.csv`: 15,000 filas (9,000 en
auto repartidas en 3 franjas horarias, 3,000 en bicicleta y 3,000 a pie en una sola
franja — en desarrollo se validó que solo el modo auto varía de forma relevante
según la hora del día). El script es reanudable: identifica cada trayecto por
coordenadas redondeadas, no por IDs del catálogo, así que sigue siendo válido
aunque se vuelva a scrapear y cambien los IDs.

### Entrenamiento: `ml_pipeline/train_travel_time.py`

Entrena un XGBoost de regresión sobre `log1p(tiempo_real)` (el objetivo tiene una
cola larga y esto lo estabiliza). Como entrada usa exactamente lo que ya se conoce
antes de llamar a TomTom: el tiempo y distancia de OSRM, el modo, la hora, el día,
y la geografía relativa al centro de Lima de origen y destino — es decir, lo mismo
que hay disponible en producción al momento de inferir.

Se valida con `GroupKFold` agrupado por `workplace_id`, para medir qué tan bien
generaliza a centros de trabajo que el modelo nunca vio durante el entrenamiento
(no solo a filas nuevas de los mismos centros). Resultados (out-of-fold):

| Método | MAE | R² |
|---|---|---|
| OSRM crudo (sin corregir) | 13.52 min | 0.854 |
| Regresión lineal (log-tiempo) | 9.96 min | 0.767 |
| **XGBoost (log-tiempo)** | **3.76 min** | **0.984** |

### Inferencia: `ml_pipeline/predictor_travel_time.py`

Un singleton (`predictor_travel_time`) carga el modelo (`xgboost_travel_time.json`)
y las columnas de features (`travel_time_features.pkl`) una sola vez al arrancar.
`predict_minutes(rows)` recibe una lista de filas y devuelve el tiempo corregido
para cada una. Si el modelo no está disponible (por ejemplo en un entorno donde no
se copiaron los artefactos), degrada a devolver el tiempo de OSRM sin corregir en
vez de romper la recomendación.

**Solo se aplica a tiempos que vinieron de OSRM real.** Cuando OSRM falla y se cae
al fallback de Haversine (línea recta + velocidad promedio), ese tiempo NO pasa por
el modelo: se entrenó sobre salidas de OSRM, meterle una aproximación en línea recta
sería extrapolar fuera de lo que aprendió.

**Limitación conocida y documentada:** el dataset se recolectó con un solo día de
referencia (martes) y horas fijas por franja. La app no le pregunta al usuario a
qué hora sale de casa, así que en inferencia siempre se usa la punta de la mañana
(7:00 a.m.) — el caso de uso central del producto, y la franja donde OSRM sin
corregir tiene más error.

---

## 2. `match_score`: función de utilidad explícita

`calcular_match_score(tiempo_min, dist_km, precio_ratio, area_m2)` en
`app/services/recommendation_service.py` **no es un modelo**: es una fórmula fija,
determinista (sin ruido aleatorio), que combina cuatro señales sobre una base de 40
puntos:

| Factor | Peso máximo | Regla |
|---|---|---|
| Tiempo de viaje (ya corregido por el modelo) | hasta +45 | `≤45 min`: escala lineal a +45 en 0 min · `>45 min`: penaliza hasta -20 |
| Distancia en línea recta | hasta +3 | `≤2 km`: +3 · `≤5 km`: +1 · `≤15 km`: 0 · `>15 km`: -3 |
| Ajuste al presupuesto (`precio / budget`) | hasta +20 | `≤1.0`: escala a +20 en ratio 0 · `>1.0`: penaliza hasta -35 |
| Área total | hasta +5 | `≥40 m²`: +5 · `≥25 m²`: +3 · `≥15 m²`: +1 · `<15 m²`: -2 |

El resultado se acota entre 0 y 100. Al ser una fórmula explícita (no un modelo
entrenado), es completamente auditable: para cualquier resultado se puede mostrar
exactamente cuánto aportó cada factor, sin necesidad de técnicas de explicabilidad
post-hoc.

---

## 3. Flujo completo de una recomendación

`generar_recomendacion()` en `app/services/recommendation_service.py`:

1. **Pre-filtro espacial (PostGIS):** `ST_DWithin` + `ST_Distance` sobre la columna
   `Geography` de `properties`, filtrando por radio y estado `approved`.
2. **Filtro de presupuesto:** descarta las que exceden el presupuesto con 15% de
   tolerancia.
3. **Tiempo y distancia reales, en lote:** una sola llamada al servicio `/table` de
   OSRM resuelve distancia y tiempo hacia **todas** las candidatas a la vez (antes
   eran hasta cientos de llamadas secuenciales). Si la llamada falla completa, cada
   candidata cae a una estimación por Haversine.
4. **Corrección de tiempo:** las candidatas resueltas por OSRM real pasan por
   `corregir_tiempos()` (el modelo XGBoost). Las que cayeron al fallback de
   Haversine se quedan con esa estimación tal cual.
5. **`match_score`:** se calcula con el tiempo ya corregido, vía la fórmula
   explícita de la sección anterior.
6. **Orden final:** de mayor a menor `match_score`.

El mismo modelo de corrección de tiempo se reutiliza en `GET /route` (el endpoint
que consume el mapa para mostrar tiempo y trazar la geometría de una vivienda
seleccionada), para que el tiempo mostrado sea siempre consistente entre la lista
de recomendaciones y el detalle de una vivienda.

---

## Archivos relevantes

| Archivo | Rol |
|---|---|
| `scripts/collect_traffic_data.py` | Genera `data/processed/travel_time_dataset.csv` (OSRM + TomTom) |
| `scripts/validar_coordenadas.py` | Valida que los centros de trabajo caigan sobre la red vial real |
| `ml_pipeline/train_travel_time.py` | Entrena y valida el modelo de corrección de tiempo |
| `ml_pipeline/predictor_travel_time.py` | Carga el modelo y expone `predict_minutes()` en producción |
| `ml_pipeline/model/xgboost_travel_time.json` | Modelo serializado |
| `ml_pipeline/model/travel_time_features.pkl` | Orden de columnas esperado por el modelo |
| `app/services/recommendation_service.py` | Orquesta el flujo completo y define `calcular_match_score` |
| `app/api/route.py` | Endpoint `GET /route`, reutiliza el mismo modelo de corrección |
