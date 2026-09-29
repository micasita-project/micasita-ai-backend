# NDCG@5 — recomputado desde datos crudos

Generado por `scripts/compute_ndcg5.py` a partir de `data/raw/NDCG5_Evaluacion_MiCasita_2026_Final.xlsx` (hoja `Escenarios_Evaluacion`, 20 escenarios x 10 viviendas candidatas = 200 filas).

Relevancia por tramos según el ranking humano: 1.0 (puestos 1-2), 0.5 (puestos 3-5), 0 (puestos 6-10); coincide con la columna "Relevancia (calc.)" de la hoja en las 200 filas. IDCG@5 usa el orden ideal de cada escenario. Los baselines ordenan por precio ascendente y por tiempo OSRM crudo ascendente, con desempate por el orden del modelo.

| Escenario | NDCG@5 modelo | NDCG@5 precio | NDCG@5 OSRM crudo |
|---|---|---|---|
| 1 | 0.8375 | 0.1937 | 0.8908 |
| 2 | 0.8185 | 0.6031 | 0.7123 |
| 3 | 0.8063 | 0.6248 | 0.7912 |
| 4 | 0.8718 | 0.4541 | 0.6590 |
| 5 | 1.0000 | 0.5251 | 0.8869 |
| 6 | 0.9060 | 0.8774 | 0.6573 |
| 7 | 0.8718 | 0.0940 | 0.8718 |
| 8 | 0.9563 | 0.7435 | 0.7244 |
| 9 | 0.8471 | 0.7665 | 0.8375 |
| 10 | 0.7912 | 0.5784 | 0.6686 |
| 11 | 0.7665 | 0.4351 | 0.7665 |
| 12 | 0.9563 | 0.6837 | 0.5745 |
| 13 | 1.0000 | 0.7912 | 0.7123 |
| 14 | 0.8869 | 0.8063 | 0.5745 |
| 15 | 0.6972 | 0.5442 | 0.6972 |
| 16 | 0.7777 | 0.4939 | 0.7912 |
| 17 | 0.8869 | 0.6837 | 0.8869 |
| 18 | 0.8869 | 0.4008 | 0.5308 |
| 19 | 0.8063 | 0.7665 | 0.7721 |
| 20 | 0.9563 | 0.8375 | 0.7123 |

**NDCG@5 promedio (N=20): modelo 0.8664** (mínimo 0.6972, máximo 1.0000); baseline precio 0.5952; baseline OSRM crudo 0.7359.

El modelo supera al baseline de precio en 20 de 20 escenarios y al de OSRM crudo en 14 (4 empates, 2 por debajo).
