"""Genera los gráficos del README (docs/img/) a partir de la base del dashboard.

    python scripts/graficos_readme.py

Son una foto del último día con datos: hay que volver a correrlo y commitear las imágenes cuando se actualicen los hallazgos
del README. Requiere haber corrido `python -m src.exportar`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
BASE = RAIZ / "data" / "dashboard" / "dashboard.duckdb"
SALIDA = RAIZ / "docs" / "img"
COLOR, RESALTADO = "#4C78A8", "#E45756"

plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})


def ranking_canasta(con) -> Path:
    t = con.execute("""
        select cadena, costo_canasta::double as costo, sobre_la_mas_barata_pct as sobre, posicion, fecha
        from m_ranking_canasta_dia
        where zona = 'TODAS' and fecha = (select max(fecha) from m_ranking_canasta_dia where zona = 'TODAS')
        order by posicion desc
    """).df()
    fecha = t["fecha"].iloc[0]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.barh(t["cadena"], t["costo"], color=[RESALTADO if p == 1 else COLOR for p in t["posicion"]])
    for y, (costo, sobre) in enumerate(zip(t["costo"], t["sobre"])):
        ax.text(costo, y, f"  ${costo:,.0f}".replace(",", ".") + ("" if sobre == 0 else f"  (+{sobre:.1f}%)".replace(".", ",")),
                va="center", fontsize=8)
    ax.set_xlim(0, t["costo"].max() * 1.3)
    ax.set_xlabel("Costo de la canasta de 30 productos ($)")
    ax.set_title(f"Costo de la misma canasta por cadena, CABA y GBA ({fecha:%d/%m/%Y})", fontsize=10)
    fig.tight_layout()
    ruta = SALIDA / "ranking_canasta.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def dispersion(con) -> Path:
    t = con.execute("""
        select k.producto, median(d.rango_pct) as rango
        from m_dispersion_producto_dia d join dim_canasta k using (clave_producto)
        where d.zona = 'TODAS' group by k.producto order by rango desc limit 10
    """).df().sort_values("rango")
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.barh(t["producto"], t["rango"], color=COLOR)
    for y, v in enumerate(t["rango"]):
        ax.text(v, y, f"  {v:.0f}%", va="center", fontsize=8)
    ax.set_xlim(0, t["rango"].max() * 1.15)
    ax.set_xlabel("% más caro en la cadena más cara que en la más barata")
    ax.set_title("Productos con más diferencia de precio entre cadenas", fontsize=10)
    fig.tight_layout()
    ruta = SALIDA / "dispersion_productos.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def main() -> int:
    if not BASE.exists():
        print(f"No existe {BASE}: primero correr python -m src.exportar")
        return 1
    SALIDA.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(BASE), read_only=True)
    for ruta in (ranking_canasta(con), dispersion(con)):
        print("Guardado", ruta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
