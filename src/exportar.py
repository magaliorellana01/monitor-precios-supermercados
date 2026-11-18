"""Arma la base chica que lee el dashboard (data/dashboard/dashboard.duckdb) a partir del modelo.

    python -m src.exportar

El modelo pesa cientos de MB y no se puede subir a git ni a Streamlit Cloud. El dashboard solo necesita las
métricas ya calculadas (unos cientos de KB), así que acá se copian esas tablas, se agrega el IPC si está bajado
y una tabla `meta` con la fecha de generación y el rango de días. Después `src.almacen.subir_dashboard()` la sube
al Release `datos-dashboard`, de donde la baja la app.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import duckdb

from . import ingesta, modelo

DIR_DASHBOARD = ingesta.DIR_DATOS / "dashboard"
RUTA_DASHBOARD = DIR_DASHBOARD / "dashboard.duckdb"
RUTA_IPC = ingesta.DIR_DATOS / "externos" / "ipc.csv"

log = logging.getLogger("exportar")

# Tablas del modelo que se copian tal cual.
TABLAS = (
    "m_canasta_dia",
    "m_ranking_canasta_dia",
    "m_indice_cadena_dia",
    "m_indice_general_dia",
    "m_prima_marca_dia",
    "m_promo_cadena_dia",
    "dim_canasta",
    "dim_par_marca",
)

# Tablas que se arman con una consulta: solo productos de la canasta, que son los que muestra el dashboard.
CONSULTAS = {
    "m_dispersion_producto_dia": """
        select d.* from m.m_dispersion_producto_dia d
        join m.dim_canasta k using (clave_producto)
    """,
    "precio_canasta_dia": """
        select r.fecha, r.cadena, r.zona, r.clave_producto, k.categoria, k.producto, r.n_sucursales,
               r.precio_mediana
        from m.fct_precio_representativo r
        join m.dim_canasta k using (clave_producto)
        join m.m_cadena_dia c using (fecha, cadena, zona)
        where c.comparable
    """,
}


def exportar(ruta_modelo: Path | None = None, ruta: Path | None = None, ruta_ipc: Path | None = None) -> Path:
    ruta_modelo = ruta_modelo or modelo.RUTA_MODELO
    ruta = ruta or RUTA_DASHBOARD
    ruta_ipc = ruta_ipc or RUTA_IPC
    if not ruta_modelo.exists():
        raise FileNotFoundError(f"No existe {ruta_modelo}: primero hay que correr python -m src.modelo")

    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists():
        ruta.unlink()

    con = duckdb.connect(str(ruta))
    try:
        con.execute(f"attach '{ruta_modelo.as_posix()}' as m (read_only)")
        for tabla in TABLAS:
            con.execute(f"create table {tabla} as select * from m.{tabla}")
        for tabla, consulta in CONSULTAS.items():
            con.execute(f"create table {tabla} as {consulta}")

        if ruta_ipc.exists():
            con.execute(
                "create table ipc as select fecha::date as fecha, variacion_mensual_pct::double as variacion_mensual_pct "
                f"from read_csv('{ruta_ipc.as_posix()}', header = true)")
        else:
            log.warning("No está %s: el dashboard va a salir sin IPC (python -m src.ipc)", ruta_ipc)
            con.execute("create table ipc (fecha date, variacion_mensual_pct double)")

        con.execute("""
            create table meta as
            select now()::timestamp as generado_en,
                   min(fecha) as fecha_desde, max(fecha) as fecha_hasta, count(distinct fecha)::integer as dias
            from m.m_canasta_dia
        """)
        con.execute("detach m")
    finally:
        con.close()
    log.info("Base del dashboard lista en %s (%.2f MB)", ruta, ruta.stat().st_size / 1e6)
    return ruta


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        exportar()
    except (FileNotFoundError, duckdb.Error) as e:
        log.error("No se pudo armar la base del dashboard: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
