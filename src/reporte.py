"""Reporte semanal de precios, en Markdown.

    python -m src.reporte                       # la última semana completa (lunes a domingo) que no tenga reporte
    python -m src.reporte --semana 2026-11-16   # la semana que contiene esa fecha
    python -m src.reporte --parcial             # la semana en curso, con los días que haya

Lee la base chica del dashboard (data/dashboard/dashboard.duckdb), así que va después de `python -m src.exportar`.
Las consultas están en sql/06_reporte/. Guarda reports/semanal/AAAA-MM-DD.md (la fecha es el lunes) y lo sube al
Release `reportes-semanales`. La tarea diaria lo genera sola cuando termina una semana.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb

from . import calidad, exportar, ingesta

DIR_REPORTES = ingesta.RAIZ / "reports" / "semanal"
DIR_SQL = ingesta.RAIZ / "sql" / "06_reporte"

MIN_CADENAS_PRODUCTO = 5   # cadenas que tienen que informar un producto para mostrar su variación
MIN_FILAS_PROMO = 1000     # precios en promoción por día para mostrar una cadena
CANTIDAD_PRODUCTOS = 5     # productos que más subieron y que más bajaron
MIN_DIAS_AUTOMATICO = 5    # días con datos que tiene que tener una semana para que el reporte salga solo

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]

log = logging.getLogger("reporte")


class SinSemana(Exception):
    """No hay datos para armar el reporte pedido."""


# --------------------------------------------------------------------------- fechas

def lunes_de(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def ultima_semana_completa(ultimo_dia: date) -> date:
    """Lunes de la última semana cuyo domingo ya pasó (o es el último día con datos)."""
    lunes = lunes_de(ultimo_dia)
    if ultimo_dia - lunes >= timedelta(days=6):
        return lunes
    return lunes - timedelta(days=7)


def ruta_reporte(lunes: date, carpeta: Path | None = None) -> Path:
    return (carpeta or DIR_REPORTES) / f"{lunes.isoformat()}.md"


def fecha_larga(f: date) -> str:
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


def rango_semana(lunes: date, domingo: date) -> str:
    if lunes.month == domingo.month:
        return f"{lunes.day} al {domingo.day} de {MESES[lunes.month - 1]} de {lunes.year}"
    return f"{fecha_larga(lunes)} al {fecha_larga(domingo)}"


# --------------------------------------------------------------------------- formato

def peso(x: float) -> str:
    return "$ " + f"{x:,.0f}".replace(",", ".")


def pct(x: float | None, signo: bool = False) -> str:
    if x is None or x != x:
        return "—"
    if round(x, 1) == 0:
        signo = False  # "+0,0 %" no dice nada; "0,0 %" sí
        x = 0.0
    texto = f"{x:+.1f}" if signo else f"{x:.1f}"
    return texto.replace(".", ",") + " %"


def numero(x: float, decimales: int = 2) -> str:
    return f"{x:.{decimales}f}".replace(".", ",")


def tabla(encabezados: list[str], filas: list[list[str]]) -> str:
    lineas = ["| " + " | ".join(encabezados) + " |", "|" + "|".join("---" for _ in encabezados) + "|"]
    lineas += ["| " + " | ".join(f) + " |" for f in filas]
    return "\n".join(lineas)


# --------------------------------------------------------------------------- consultas

def correr(con: duckdb.DuckDBPyConnection, nombre: str, **parametros):
    sql = (DIR_SQL / nombre).read_text(encoding="utf-8")
    return con.execute(sql, parametros).df()


def fechas_con_datos(con: duckdb.DuckDBPyConnection) -> list[date]:
    return [f for (f,) in con.execute("select distinct fecha from m_canasta_dia order by fecha").fetchall()]


def elegir_fechas(disponibles: list[date], lunes: date) -> tuple[date, date, bool]:
    """Devuelve (hasta, base, hay_semana_anterior).

    `hasta` es el último día con datos de la semana. `base` es la última fecha de la semana anterior; si no hay datos de
    la semana anterior (el proyecto recién empieza), el primer día de esta semana.
    """
    domingo = lunes + timedelta(days=6)
    de_la_semana = [f for f in disponibles if lunes <= f <= domingo]
    if not de_la_semana:
        raise SinSemana(f"No hay datos entre el {lunes} y el {domingo}.")
    anteriores = [f for f in disponibles if f < lunes]
    if anteriores:
        return max(de_la_semana), max(anteriores), True
    return max(de_la_semana), min(de_la_semana), False


# --------------------------------------------------------------------------- armado del texto

def armar(con: duckdb.DuckDBPyConnection, lunes: date, ruta_log_calidad: Path | None = None) -> str:
    domingo = lunes + timedelta(days=6)
    disponibles = fechas_con_datos(con)
    hasta, base, hay_anterior = elegir_fechas(disponibles, lunes)

    canasta = correr(con, "01_canasta.sql", hasta=hasta, base=base)
    indice = correr(con, "02_indice.sql", hasta=hasta, base=base).iloc[0]
    productos = correr(con, "03_productos.sql", hasta=hasta, base=base, min_cadenas=MIN_CADENAS_PRODUCTO)
    promos = correr(con, "04_promociones.sql", desde=lunes, hasta=hasta, min_filas=MIN_FILAS_PROMO)
    cobertura = correr(con, "05_cobertura.sql", desde=lunes, hasta=hasta).iloc[0]

    dias_con_datos = int(cobertura["dias_con_datos"])
    parcial = dias_con_datos < 7
    comparacion = (f"la semana anterior (cierre del {fecha_larga(base)})" if hay_anterior
                   else f"el primer día con datos ({fecha_larga(base)}), porque todavía no hay una semana anterior")

    out: list[str] = []
    out.append("# Reporte semanal de precios de supermercados")
    out.append(f"**Semana del {rango_semana(lunes, domingo)}** · CABA y GBA · {dias_con_datos} de 7 días con datos")
    if parcial:
        out.append(f"> **Semana incompleta:** hay datos de {dias_con_datos} de los 7 días. Las cifras valen para los días que hay.")

    # ---- resumen
    out.append("## Resumen")
    resumen: list[str] = []
    if canasta.empty:
        resumen.append("No hay cadenas con la canasta completa para comparar al cierre de la semana.")
    else:
        barata, cara = canasta.iloc[0], canasta.iloc[-1]
        diferencia = 100 * (cara["costo"] / barata["costo"] - 1)
        resumen.append(f"**Canasta más barata:** {barata['cadena']} ({peso(barata['costo'])}). **Más cara:** {cara['cadena']} "
                       f"({peso(cara['costo'])}), un {pct(diferencia)} más.")
        movimientos = canasta.dropna(subset=["posicion_base"])
        movimientos = movimientos[movimientos["posicion"] != movimientos["posicion_base"]]
        if hay_anterior and not movimientos.empty:
            cambios = ", ".join(f"{f['cadena']} ({int(f['posicion_base'])}° → {int(f['posicion'])}°)" for _, f in movimientos.iterrows())
            resumen.append(f"**Cambios de posición:** {cambios}.")
        elif hay_anterior:
            resumen.append("**Posiciones:** el ranking de cadenas no cambió respecto de la semana anterior.")
    if indice["indice_hasta"] == indice["indice_hasta"] and indice["variacion_pct"] == indice["variacion_pct"]:
        resumen.append(f"**Índice de la canasta:** {numero(indice['indice_hasta'])} ({pct(indice['variacion_pct'], True)} frente a {comparacion}).")
    suben = productos[productos["variacion_pct"] > 0]
    bajan = productos[productos["variacion_pct"] < 0]
    if not productos.empty:
        if suben.empty and bajan.empty:
            resumen.append("**Productos:** ninguno de los 30 de la canasta cambió de precio.")
        else:
            resumen.append(f"**Productos:** {len(suben)} subieron y {len(bajan)} bajaron de precio (de 30).")
    out.append("\n".join(f"- {r}" for r in resumen))

    # ---- 1. canasta
    out.append("## 1. Costo de la canasta por cadena")
    if canasta.empty:
        out.append("Sin datos suficientes.")
    else:
        filas = []
        for _, f in canasta.iterrows():
            filas.append([f"{int(f['posicion'])}°", f["cadena"], peso(f["costo"]),
                          "la más barata" if f["posicion"] == 1 else pct(f["sobre_la_mas_barata_pct"], True),
                          pct(f["variacion_pct"], True),
                          "—" if f["posicion_base"] != f["posicion_base"] else f"{int(f['posicion_base'])}°"])
        out.append(tabla(["Puesto", "Cadena", f"Costo al {hasta:%d/%m}", "Sobre la más barata",
                          "Cambio en el período", "Puesto antes"], filas))
        out.append(f"Costo de comprar una unidad de cada uno de los 30 productos de la canasta, con el precio de lista mediano de cada cadena. "
                   f"El cambio se mide contra {comparacion}.")

    # ---- 2. índice
    out.append("## 2. Índice de precios")
    if indice["indice_hasta"] != indice["indice_hasta"]:
        out.append("Todavía no hay índice para estas fechas.")
    else:
        out.append(f"El índice de la canasta (base 100 el día de arranque) cerró la semana en **{numero(indice['indice_hasta'])}**"
                   + (f", {pct(indice['variacion_pct'], True)} frente a {comparacion}." if indice["variacion_pct"] == indice["variacion_pct"] else "."))
        out.append("Los precios de supermercado se actualizan en saltos: una semana sin cambios no contradice una inflación mensual positiva.")

    # ---- 3. productos
    out.append("## 3. Productos que más cambiaron")
    if productos.empty:
        out.append("No hay productos con suficientes cadenas informando en las dos fechas.")
    else:
        for titulo, datos in (("Los que más subieron", suben.head(CANTIDAD_PRODUCTOS)),
                              ("Los que más bajaron", bajan.sort_values("variacion_pct").head(CANTIDAD_PRODUCTOS))):
            out.append(f"**{titulo}**")
            if datos.empty:
                out.append("Ninguno.")
            else:
                out.append(tabla(["Producto", "Categoría", "Precio antes", "Precio ahora", "Cambio"],
                                 [[f["producto"], f["categoria"], peso(f["precio_base"]), peso(f["precio_hasta"]),
                                   pct(f["variacion_pct"], True)] for _, f in datos.iterrows()]))
        out.append("Cambio de la mediana entre cadenas del precio de lista, solo con productos informados por al menos "
                   f"{MIN_CADENAS_PRODUCTO} cadenas.")

    # ---- 4. promociones
    out.append("## 4. Promociones")
    if promos.empty:
        out.append("Ninguna cadena informó suficientes promociones en la semana.")
    else:
        out.append(tabla(["Cadena", "Precios en promoción", "Descuento mediano", "Días"],
                         [[f["cadena"], pct(f["pct_con_promo"]), pct(f["descuento_mediano_pct"]), str(int(f["dias"]))]
                          for _, f in promos.iterrows()]))
        out.append("Solo informan promociones algunas cadenas; las demás no se pueden comparar. "
                   "Si las ofertas son \"el precio de siempre\" se mira en el análisis, con más semanas de historia.")

    # ---- 5. calidad
    out.append("## 5. Calidad de los datos")
    calidad_lineas = [f"- **Días con datos:** {dias_con_datos} de 7.",
                      f"- **Cadenas comparadas al cierre:** {int(cobertura['cadenas_comparadas'])}."]
    if int(cobertura["dias_con_canasta_incompleta"]):
        calidad_lineas.append(f"- **Canasta incompleta:** en {int(cobertura['dias_con_canasta_incompleta'])} día(s) alguna cadena comparable "
                              "no tuvo los 30 productos; si faltaba poco, se usó su último precio.")
    ruta_log = ruta_log_calidad or calidad.RUTA_LOG
    if ruta_log.exists():
        avisos = correr(duckdb.connect(), "06_avisos_calidad.sql", ruta=str(ruta_log), desde=lunes.isoformat(), hasta=hasta.isoformat())
        if avisos.empty:
            calidad_lineas.append("- **Controles de calidad:** sin advertencias.")
        else:
            calidad_lineas.append("- **Controles de calidad:** " + "; ".join(
                f"{f['control']} ({f['resultado']}, {int(f['dias'])} día(s))" for _, f in avisos.iterrows()) + ".")
    else:
        calidad_lineas.append("- **Controles de calidad:** no se encontró el log de la ingesta en esta PC.")
    out.append("\n".join(calidad_lineas))

    out.append("---")
    out.append("Son precios **informados por las cadenas** a SEPA (Precios Claros), no de tickets reales. "
               "Canasta fija de 30 productos de marca nacional, una unidad de cada uno, mediana entre sucursales. "
               "Metodología y decisiones: `docs/decisiones.md`.")
    return "\n\n".join(out) + "\n"


# --------------------------------------------------------------------------- generación

def generar(lunes: date, ruta_dashboard: Path | None = None, carpeta: Path | None = None,
            ruta_log_calidad: Path | None = None) -> Path:
    ruta_dashboard = ruta_dashboard or exportar.RUTA_DASHBOARD
    if not ruta_dashboard.exists():
        raise FileNotFoundError(f"No existe {ruta_dashboard}: primero hay que correr python -m src.exportar")
    con = duckdb.connect(str(ruta_dashboard), read_only=True)
    try:
        texto = armar(con, lunes, ruta_log_calidad)
    finally:
        con.close()
    ruta = ruta_reporte(lunes, carpeta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    log.info("Reporte guardado en %s", ruta)
    return ruta


def generar_si_corresponde(ruta_dashboard: Path | None = None, carpeta: Path | None = None,
                           ruta_log_calidad: Path | None = None) -> Path | None:
    """Genera el reporte de la última semana completa si todavía no existe. Devuelve su ruta, o None si no había nada que hacer."""
    ruta_dashboard = ruta_dashboard or exportar.RUTA_DASHBOARD
    con = duckdb.connect(str(ruta_dashboard), read_only=True)
    try:
        disponibles = fechas_con_datos(con)
    finally:
        con.close()
    if not disponibles:
        return None
    lunes = ultima_semana_completa(max(disponibles))
    if ruta_reporte(lunes, carpeta).exists():
        return None
    # Una semana con muy pocos días (por ejemplo, la primera del proyecto) no se reporta sola: se puede pedir a mano.
    if sum(lunes <= f <= lunes + timedelta(days=6) for f in disponibles) < MIN_DIAS_AUTOMATICO:
        return None
    return generar(lunes, ruta_dashboard, carpeta, ruta_log_calidad)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--semana", type=date.fromisoformat, help="una fecha de la semana a reportar (AAAA-MM-DD)")
    parser.add_argument("--parcial", action="store_true", help="la semana en curso, con los días que haya")
    parser.add_argument("--sin-subir", action="store_true", help="no sube el reporte al Release")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    from . import almacen

    try:
        if args.semana:
            lunes = lunes_de(args.semana)
        else:
            con = duckdb.connect(str(exportar.RUTA_DASHBOARD), read_only=True)
            try:
                ultimo = max(fechas_con_datos(con))
            finally:
                con.close()
            lunes = lunes_de(ultimo) if args.parcial else ultima_semana_completa(ultimo)
        ruta = generar(lunes)
        if not args.sin_subir:
            almacen.subir_reporte(ruta)
    except (SinSemana, FileNotFoundError, duckdb.Error, ValueError) as e:
        log.error("No se pudo armar el reporte: %s", e)
        return 1
    except almacen.ErrorGh as e:
        log.error("El reporte quedó guardado pero no se pudo subir al Release: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
