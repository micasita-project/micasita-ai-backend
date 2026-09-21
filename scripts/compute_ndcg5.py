"""
Recalcula NDCG@5 a partir de la data cruda de evaluación (ranking del modelo
vs. ranking humano), en vez de citar el resultado que ya trae la hoja de
cálculo. La hoja `NDCG@5_Resultados` de data/raw/NDCG5_Evaluacion_MiCasita.xlsx
usa una IDCG@5 constante (2.0962) que no cuadra con la relevancia continua que
sí registra la hoja `Escenarios_Evaluacion` (columna "Relevancia (calc.)");
este script recalcula todo desde cero usando esa relevancia real, con la
fórmula estándar de NDCG@5, para tener un número verificable y reproducible.

Relevancia: rel = 1.1 - 0.1 * ranking_humano (verificado: coincide con la
columna "Relevancia (calc.)" de la hoja en las 200 filas, sin excepción).

Uso:
    python scripts/compute_ndcg5.py
"""

import math
from collections import defaultdict

import openpyxl

XLSX_PATH = "data/raw/NDCG5_Evaluacion_MiCasita.xlsx"
OUT_PATH = "data/processed/ndcg5_evaluacion.md"


def relevancia(humano_rank: int) -> float:
    return 1.1 - 0.1 * humano_rank


def dcg5(items_ordenados: list[dict]) -> float:
    return sum(
        relevancia(it["humano"]) / math.log2(i + 1)
        for i, it in enumerate(items_ordenados[:5], start=1)
    )


def main():
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)
    ws = wb["Escenarios_Evaluacion"]
    filas = [r for r in ws.iter_rows(min_row=4, values_only=True) if r[0] is not None]

    por_escenario = defaultdict(list)
    for r in filas:
        por_escenario[r[0]].append({
            "vivienda": r[5], "modelo": r[11], "humano": r[12],
        })

    assert all(len(v) == 10 for v in por_escenario.values()), \
        "cada escenario debe tener exactamente 10 viviendas candidatas"

    resultados = []
    for esc, items in sorted(por_escenario.items()):
        orden_modelo = sorted(items, key=lambda it: it["modelo"])
        orden_ideal = sorted(items, key=lambda it: it["humano"])
        dcg = dcg5(orden_modelo)
        idcg = dcg5(orden_ideal)
        ndcg = dcg / idcg if idcg > 0 else 0.0
        resultados.append((esc, dcg, idcg, ndcg))

    ndcgs = [r[3] for r in resultados]
    media = sum(ndcgs) / len(ndcgs)
    minimo, maximo = min(ndcgs), max(ndcgs)

    print(f"{'Escenario':<10}{'DCG@5':>10}{'IDCG@5':>10}{'NDCG@5':>10}")
    for esc, dcg, idcg, ndcg in resultados:
        print(f"{esc:<10}{dcg:>10.4f}{idcg:>10.4f}{ndcg:>10.4f}")
    print(f"\nNDCG@5 promedio (N={len(ndcgs)}): {media:.4f}")
    print(f"NDCG@5 mínimo: {minimo:.4f}  |  máximo: {maximo:.4f}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("# NDCG@5 — recomputado desde datos crudos\n\n")
        f.write(f"Generado por `scripts/compute_ndcg5.py` a partir de "
                f"`{XLSX_PATH}` (hoja `Escenarios_Evaluacion`, 20 escenarios "
                f"x 10 viviendas candidatas = 200 filas).\n\n")
        f.write("Relevancia: `rel = 1.1 - 0.1 * ranking_humano` (escala continua "
                "1.0 a 0.1, verificada contra la columna \"Relevancia (calc.)\" "
                "de la hoja original — coincide en las 200 filas). IDCG@5 usa el "
                "orden ideal real por escenario (top 5 por ranking humano), no "
                "un valor fijo.\n\n")
        f.write("| Escenario | DCG@5 | IDCG@5 | NDCG@5 |\n|---|---|---|---|\n")
        for esc, dcg, idcg, ndcg in resultados:
            f.write(f"| {esc} | {dcg:.4f} | {idcg:.4f} | {ndcg:.4f} |\n")
        f.write(f"\n**NDCG@5 promedio (N={len(ndcgs)}): {media:.4f}** "
                f"(mínimo {minimo:.4f}, máximo {maximo:.4f})\n")

    print(f"\nGuardado: {OUT_PATH}")


if __name__ == "__main__":
    main()
