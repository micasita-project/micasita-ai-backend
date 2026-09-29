"""
Recalcula NDCG@5 del modelo y de los dos baselines (precio y tiempo OSRM
crudo) a partir de la data cruda de evaluación, en vez de citar los resultados
que ya trae la hoja de cálculo.

Relevancia por tramos según el ranking humano: 1.0 si el humano puso la
vivienda en 1-2, 0.5 si en 3-5 y 0 si en 6-10. IDCG@5 se calcula por escenario
con el orden ideal (ranking humano).

Los baselines ordenan las mismas 10 viviendas por precio ascendente y por
tiempo OSRM crudo ascendente; los empates se resuelven con el orden del modelo.

Uso:
    python scripts/compute_ndcg5.py
"""

import math
from collections import defaultdict

import openpyxl

XLSX_PATH = "data/raw/NDCG5_Evaluacion_MiCasita_2026_Final.xlsx"
OUT_PATH = "data/processed/ndcg5_evaluacion.md"

COL_ESCENARIO, COL_VIVIENDA, COL_PRECIO, COL_T_OSRM = 0, 6, 8, 12
COL_MODELO, COL_HUMANO, COL_RELEVANCIA = 13, 14, 15
COL_BASE_PRECIO, COL_BASE_OSRM = 16, 17


def relevancia(humano_rank: int) -> float:
    if humano_rank <= 2:
        return 1.0
    if humano_rank <= 5:
        return 0.5
    return 0.0


def dcg5(items_ordenados: list[dict]) -> float:
    return sum(
        it["rel"] / math.log2(i + 1)
        for i, it in enumerate(items_ordenados[:5], start=1)
    )


def ndcg5(items: list[dict], clave_orden) -> float:
    idcg = dcg5(sorted(items, key=lambda it: it["humano"]))
    return dcg5(sorted(items, key=clave_orden)) / idcg if idcg > 0 else 0.0


def main():
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)
    ws = wb["Escenarios_Evaluacion"]
    filas = [r for r in ws.iter_rows(min_row=4, values_only=True) if r[COL_ESCENARIO] is not None]

    por_escenario = defaultdict(list)
    for r in filas:
        por_escenario[r[COL_ESCENARIO]].append({
            "modelo": r[COL_MODELO], "humano": r[COL_HUMANO],
            "precio": r[COL_PRECIO], "t_osrm": r[COL_T_OSRM],
            "rel": relevancia(r[COL_HUMANO]),
            "rel_hoja": r[COL_RELEVANCIA],
            "base_precio_hoja": r[COL_BASE_PRECIO], "base_osrm_hoja": r[COL_BASE_OSRM],
        })

    assert all(len(v) == 10 for v in por_escenario.values()), \
        "cada escenario debe tener exactamente 10 viviendas candidatas"
    assert all(it["rel"] == it["rel_hoja"] for v in por_escenario.values() for it in v), \
        "la relevancia por tramos debe coincidir con la columna 'Relevancia (calc.)'"

    resultados = []
    for esc, items in sorted(por_escenario.items()):
        # Los baselines se recomputan desde precio y tiempo; el desempate usa el orden del modelo.
        orden_precio = sorted(items, key=lambda it: (it["precio"], it["modelo"]))
        orden_osrm = sorted(items, key=lambda it: (it["t_osrm"], it["modelo"]))
        assert [it["base_precio_hoja"] for it in orden_precio] == list(range(1, 11)), \
            f"escenario {esc}: el ranking por precio de la hoja no coincide"
        assert [it["base_osrm_hoja"] for it in orden_osrm] == list(range(1, 11)), \
            f"escenario {esc}: el ranking por tiempo OSRM de la hoja no coincide"

        resultados.append((
            esc,
            ndcg5(items, lambda it: it["modelo"]),
            ndcg5(items, lambda it: (it["precio"], it["modelo"])),
            ndcg5(items, lambda it: (it["t_osrm"], it["modelo"])),
        ))

    n = len(resultados)
    media = lambda idx: sum(r[idx] for r in resultados) / n
    m_modelo, m_precio, m_osrm = media(1), media(2), media(3)
    eps = 1e-9
    gana_precio = sum(r[1] > r[2] + eps for r in resultados)
    gana_osrm = sum(r[1] > r[3] + eps for r in resultados)
    empata_osrm = sum(abs(r[1] - r[3]) <= eps for r in resultados)
    pierde_osrm = sum(r[1] < r[3] - eps for r in resultados)
    minimo = min(r[1] for r in resultados)
    maximo = max(r[1] for r in resultados)

    print(f"{'Escenario':<10}{'Modelo':>10}{'Precio':>10}{'OSRM':>10}")
    for esc, mod, pre, osrm in resultados:
        print(f"{esc:<10}{mod:>10.4f}{pre:>10.4f}{osrm:>10.4f}")
    print(f"\nNDCG@5 promedio (N={n}): modelo {m_modelo:.4f} | precio {m_precio:.4f} | OSRM crudo {m_osrm:.4f}")
    print(f"Modelo: mínimo {minimo:.4f}, máximo {maximo:.4f}")
    print(f"Supera a precio en {gana_precio}/{n}; a OSRM en {gana_osrm} "
          f"({empata_osrm} empates, {pierde_osrm} por debajo)")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("# NDCG@5 — recomputado desde datos crudos\n\n")
        f.write(f"Generado por `scripts/compute_ndcg5.py` a partir de "
                f"`{XLSX_PATH}` (hoja `Escenarios_Evaluacion`, {n} escenarios "
                f"x 10 viviendas candidatas = {n * 10} filas).\n\n")
        f.write("Relevancia por tramos según el ranking humano: 1.0 (puestos 1-2), "
                "0.5 (puestos 3-5), 0 (puestos 6-10); coincide con la columna "
                "\"Relevancia (calc.)\" de la hoja en las 200 filas. IDCG@5 usa el "
                "orden ideal de cada escenario. Los baselines ordenan por precio "
                "ascendente y por tiempo OSRM crudo ascendente, con desempate por el "
                "orden del modelo.\n\n")
        f.write("| Escenario | NDCG@5 modelo | NDCG@5 precio | NDCG@5 OSRM crudo |\n|---|---|---|---|\n")
        for esc, mod, pre, osrm in resultados:
            f.write(f"| {esc} | {mod:.4f} | {pre:.4f} | {osrm:.4f} |\n")
        f.write(f"\n**NDCG@5 promedio (N={n}): modelo {m_modelo:.4f}** "
                f"(mínimo {minimo:.4f}, máximo {maximo:.4f}); "
                f"baseline precio {m_precio:.4f}; baseline OSRM crudo {m_osrm:.4f}.\n\n")
        f.write(f"El modelo supera al baseline de precio en {gana_precio} de {n} escenarios "
                f"y al de OSRM crudo en {gana_osrm} ({empata_osrm} empates, "
                f"{pierde_osrm} por debajo).\n")

    print(f"\nGuardado: {OUT_PATH}")


if __name__ == "__main__":
    main()
