# NDCG@5 — recomputado desde datos crudos

Generado por `scripts/compute_ndcg5.py` a partir de `data/raw/NDCG5_Evaluacion_MiCasita.xlsx` (hoja `Escenarios_Evaluacion`, 20 escenarios x 10 viviendas candidatas = 200 filas).

Relevancia: `rel = 1.1 - 0.1 * ranking_humano` (escala continua 1.0 a 0.1, verificada contra la columna "Relevancia (calc.)" de la hoja original — coincide en las 200 filas). IDCG@5 usa el orden ideal real por escenario (top 5 por ranking humano), no un valor fijo.

| Escenario | DCG@5 | IDCG@5 | NDCG@5 |
|---|---|---|---|
| 1 | 2.4558 | 2.5014 | 0.9818 |
| 2 | 2.4496 | 2.5014 | 0.9793 |
| 3 | 2.3758 | 2.5014 | 0.9498 |
| 4 | 2.4558 | 2.5014 | 0.9818 |
| 5 | 2.4627 | 2.5014 | 0.9845 |
| 6 | 2.4558 | 2.5014 | 0.9818 |
| 7 | 2.4496 | 2.5014 | 0.9793 |
| 8 | 2.4558 | 2.5014 | 0.9818 |
| 9 | 2.3627 | 2.5014 | 0.9446 |
| 10 | 2.4558 | 2.5014 | 0.9818 |
| 11 | 2.3996 | 2.5014 | 0.9593 |
| 12 | 2.4558 | 2.5014 | 0.9818 |
| 13 | 2.4558 | 2.5014 | 0.9818 |
| 14 | 2.3758 | 2.5014 | 0.9498 |
| 15 | 2.4496 | 2.5014 | 0.9793 |
| 16 | 2.4627 | 2.5014 | 0.9845 |
| 17 | 2.4258 | 2.5014 | 0.9698 |
| 18 | 2.4496 | 2.5014 | 0.9793 |
| 19 | 2.4558 | 2.5014 | 0.9818 |
| 20 | 2.4189 | 2.5014 | 0.9670 |

**NDCG@5 promedio (N=20): 0.9740** (mínimo 0.9446, máximo 0.9845)
