"""Modelo de datos en DuckDB: de los Parquet diarios a tablas listas para analizar (data/modelo.duckdb).

    python -m src.modelo              # carga los días nuevos y recalcula las métricas
    python -m src.modelo --rehacer    # borra el modelo y lo arma de cero con todos los días guardados

Todas las transformaciones están en SQL, en la carpeta sql/, y se corren en este orden:
    01_staging       vistas temporales sobre los Parquet y la configuración (config/)
    02_dimensiones   dim_fecha, dim_cadena, dim_sucursal, dim_producto, dim_canasta, dim_par_marca, parametros
    03_hechos        fct_precios, fct_precio_representativo, fct_cobertura_dia  (UNA VEZ POR CADA DÍA NUEVO)
    04_metricas      canasta, ranking, índice, dispersión y prima de marca  (se recalculan enteras en cada corrida)

El modelo es incremental: los hechos de un día se cargan una sola vez. Si un día se reprocesó (cambió su Parquet), se vuelve
a cargar. Las decisiones están en docs/decisiones.md (decisiones 11 a 15).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATOS = RAIZ / "data"
DIR_SQL = RAIZ / "sql"
DIR_CONFIG = RAIZ / "config"
RUTA_MODELO = DIR_DATOS / "modelo.duckdb"

CAPAS_UNICAS = ("01_staging", "02_dimensiones")
CAPA_POR_DIA = "03_hechos"
CAPA_METRICAS = "04_metricas"
TABLAS_DIARIAS = ("precios", "sucursales", "comercios", "productos")

log = logging.getLogger("modelo")


# --------------------------------------------------------------------------- lectura de SQL

def _literal(ruta: Path) -> str:
    """Ruta lista para meter dentro de un texto SQL entre comillas simples."""
    return ruta.as_posix().replace("'", "''")


def texto_sql(archivo: Path, reemplazos: dict[str, str]) -> str:
    texto = archivo.read_text(encoding="utf-8")
    for clave, valor in reemplazos.items():
        texto = texto.replace("{{" + clave + "}}", valor)
    if "{{" in texto:
        raise ValueError(f"{archivo.name}: quedó un {{{{marcador}}}} sin reemplazar")
    return texto


def correr_capa(con: duckdb.DuckDBPyConnection, capa: str, reemplazos: dict[str, str]) -> None:
    for archivo in sorted((DIR_SQL / capa).glob("*.sql")):
        inicio = time.perf_counter()
        con.execute(texto_sql(archivo, reemplazos))
        log.info("  %s/%s (%.1f s)", capa, archivo.name, time.perf_counter() - inicio)


# --------------------------------------------------------------------------- qué días hay

def fechas_disponibles(dir_datos: Path) -> dict[date, float]:
    """Días con las cuatro tablas completas en data/, con la fecha de modificación de su Parquet de precios."""
    fechas = {}
    for carpeta in (dir_datos / "precios").glob("fecha=*"):
        try:
            fecha = date.fromisoformat(carpeta.name.removeprefix("fecha="))
        except ValueError:  # carpeta temporal de una corrida interrumpida (fecha=...tmp)
            continue
        archivos = [dir_datos / t / f"fecha={fecha.isoformat()}" / f"{t}.parquet" for t in TABLAS_DIARIAS]
        if all(a.exists() for a in archivos):
            fechas[fecha] = archivos[0].stat().st_mtime
    return dict(sorted(fechas.items()))


def fechas_pendientes(con: duckdb.DuckDBPyConnection, disponibles: dict[date, float]) -> list[date]:
    """Días que todavía no están cargados, o cuyo Parquet cambió después de cargarlos (se reprocesaron)."""
    cargadas = {f: m for f, m in con.execute("select fecha, mtime_origen from modelo_fechas").fetchall()}
    return [f for f, mtime in disponibles.items() if f not in cargadas or mtime > cargadas[f] + 1]


# --------------------------------------------------------------------------- ejecución

def ejecutar(dir_datos: Path | None = None, dir_config: Path | None = None, ruta: Path | None = None,
             rehacer: bool = False) -> int:
    dir_datos = dir_datos or DIR_DATOS
    dir_config = dir_config or DIR_CONFIG
    ruta = ruta or RUTA_MODELO

    disponibles = fechas_disponibles(dir_datos)
    if not disponibles:
        log.error("No hay días guardados en %s. Primero hay que correr la ingesta (python -m src.ingesta).", dir_datos)
        return 1

    if rehacer and ruta.exists():
        ruta.unlink()
        log.info("Modelo borrado: se arma de cero")
    ruta.parent.mkdir(parents=True, exist_ok=True)

    inicio = time.perf_counter()
    con = duckdb.connect(str(ruta))
    try:
        con.execute("create table if not exists modelo_fechas (fecha date primary key, mtime_origen double, cargada_en timestamp)")

        reemplazos = {
            "DIR_DATOS": _literal(dir_datos),
            "DIR_CONFIG": _literal(dir_config),
            "FECHA_MAX": max(disponibles).isoformat(),
        }

        for capa in CAPAS_UNICAS:
            log.info("Capa %s", capa)
            correr_capa(con, capa, reemplazos)

        pendientes = fechas_pendientes(con, disponibles)
        log.info("Capa %s: %d día(s) para cargar de %d guardados", CAPA_POR_DIA, len(pendientes), len(disponibles))
        for fecha in pendientes:
            inicio_dia = time.perf_counter()
            con.begin()
            try:
                correr_capa(con, CAPA_POR_DIA, {**reemplazos, "FECHA": fecha.isoformat()})
                con.execute("delete from modelo_fechas where fecha = ?", [fecha])
                con.execute("insert into modelo_fechas values (?, ?, ?)", [fecha, disponibles[fecha], datetime.now()])
                con.commit()
            except Exception:
                con.rollback()  # el día queda sin cargar a medias
                raise
            log.info("Día %s cargado (%.0f s)", fecha, time.perf_counter() - inicio_dia)

        log.info("Capa %s", CAPA_METRICAS)
        correr_capa(con, CAPA_METRICAS, reemplazos)

        resumen(con)
        for aviso in verificar(con):
            log.warning("AVISO: %s", aviso)
    finally:
        con.close()

    log.info("Modelo listo en %s (%.1f MB, %.0f s)", ruta, ruta.stat().st_size / 1e6, time.perf_counter() - inicio)
    return 0


# --------------------------------------------------------------------------- resumen y avisos

def resumen(con: duckdb.DuckDBPyConnection) -> None:
    for tabla in ("fct_precios", "fct_precio_representativo", "fct_cobertura_dia", "dim_producto", "dim_sucursal",
                  "dim_cadena", "m_canasta_dia", "m_indice_general_dia", "m_dispersion_producto_dia",
                  "m_prima_marca_dia"):
        filas = con.execute(f"select count(*) from {tabla}").fetchall()[0][0]
        log.info("  %-28s %s filas", tabla, f"{filas:,}")


def verificar(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Cosas que no frenan el modelo pero conviene mirar."""
    avisos = []
    ultima = con.execute("select max(fecha) from fct_precios").fetchall()[0][0]

    # solo las banderas que tienen sucursales en la zona: el resto no entra en ninguna comparación
    sin_clasificar = con.execute(
        """select string_agg(distinct c.bandera_nombre || ' (' || c.id_comercio || '-' || c.id_bandera || ')', ', ')
           from dim_cadena c join dim_sucursal s using (id_comercio, id_bandera)
           where c.rubro = 'sin_clasificar'""").fetchall()[0][0]
    if sin_clasificar:
        avisos.append(f"banderas con sucursales en la zona que no están en config/cadenas.csv: {sin_clasificar}")

    faltan = con.execute(
        """select string_agg(coalesce(k.producto, k.clave_producto), '; ')
           from dim_canasta k
           where not exists (select 1 from fct_precio_representativo r
                             where r.clave_producto = k.clave_producto and r.fecha = ?)""", [ultima]).fetchall()[0][0]
    if faltan:
        avisos.append(f"productos de la canasta sin ningún precio el {ultima}: {faltan}")

    incompletas = con.execute(
        """select string_agg(cadena || ' (' || n_productos || '/' || n_productos_canasta || ')', ', ')
           from m_canasta_dia
           where fecha = ? and zona = 'TODAS' and comparable and not completa""", [ultima]).fetchall()[0][0]
    if incompletas:
        avisos.append(f"cadenas con la canasta incompleta el {ultima} (no entran en el ranking): {incompletas}")

    if con.execute("select count(*) from m_indice_cadena_dia").fetchall()[0][0] == 0:
        avisos.append("el índice quedó vacío: ninguna cadena tiene la canasta completa en fecha_base_indice "
                      "(config/parametros.csv)")

    sin_precio = con.execute(
        """select string_agg(coalesce(m.producto, m.clave_producto), '; ')
           from dim_par_marca m
           where not exists (select 1 from fct_precio_representativo r
                             where r.clave_producto = m.clave_producto and r.fecha = ?)""", [ultima]).fetchall()[0][0]
    if sin_precio:
        avisos.append(f"productos de config/marcas.csv sin ningún precio el {ultima}: {sin_precio}")
    return avisos


# --------------------------------------------------------------------------- línea de comandos

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rehacer", action="store_true", help="borrar el modelo y armarlo de cero")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)
    try:
        return ejecutar(rehacer=args.rehacer)
    except Exception:
        log.exception("El modelo falló")
        return 1


if __name__ == "__main__":
    sys.exit(main())
