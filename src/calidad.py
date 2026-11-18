"""Controles de calidad de la ingesta SEPA.

Cada control de datos es una consulta SQL en sql/calidad/ que devuelve una fila con tres columnas:
    valor    la cantidad de casos que se encontraron (o la variación en %, según el control)
    total    sobre qué universo se mide (para calcular el porcentaje)
    detalle  texto con el detalle (qué comercios, qué productos)

Acá se decide la gravedad con umbrales (ver CONTROLES y docs/decisiones.md, decisión 9):
    - "error":       el día no se guarda y el proceso termina con código de salida 1.
    - "advertencia": el día se guarda y el control queda registrado.
    - "ok":          sin problemas.

Todos los resultados (también los ok) se registran en data/calidad/log_calidad.csv.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATOS = RAIZ / "data"
DIR_SQL = RAIZ / "sql" / "calidad"
RUTA_LOG = DIR_DATOS / "calidad" / "log_calidad.csv"

OK = "ok"
ADVERTENCIA = "advertencia"
ERROR = "error"

# Días sin datos tolerados antes de considerar que el portal no se actualizó.
MAX_DIAS_PORTAL = 1


@dataclass(frozen=True)
class Control:
    """Un control de datos.

    medida:
        "cantidad"    se compara `valor` con los umbrales
        "porcentaje"  se compara 100 * valor / total
        "caida"       `valor` es una variación en %; se compara la caída (el valor sin signo negativo)
    Se avisa o se frena cuando la medida es MAYOR que el umbral. None = nunca.
    """

    nombre: str
    archivo: str
    medida: str
    advertencia: float | None
    error: float | None


CONTROLES = (
    Control("sin_precios", "00_sin_precios.sql", "cantidad", None, 0),
    Control("precios_invalidos", "02_precios_invalidos.sql", "porcentaje", 0, 1),
    Control("duplicados", "03_duplicados.sql", "porcentaje", 0, 1),
    Control("precios_absurdos", "04_precios_absurdos.sql", "porcentaje", 0, 1),
    Control("precios_sin_sucursal", "05_precios_sin_sucursal.sql", "porcentaje", 0, 5),
    Control("sucursales_sin_precios", "06_sucursales_sin_precios.sql", "porcentaje", 0, 20),
    Control("banderas_sin_comercio", "07_banderas_sin_comercio.sql", "cantidad", 0, None),
    Control("variacion_filas", "08_variacion_filas.sql", "caida", 10, 30),
    Control("banderas_ausentes", "09_banderas_ausentes.sql", "cantidad", 0, None),
    Control("caida_sucursales_bandera", "10_caida_sucursales_bandera.sql", "cantidad", 0, None),
)

# Se corre antes que el resto: si falta una columna, el SQL de la ingesta ni siquiera puede ejecutarse.
CONTROL_COLUMNAS = Control("columnas_faltantes", "01_columnas_faltantes.sql", "cantidad", None, 0)

# Orden en que se escriben los controles de una misma fecha en el log.
ORDEN_LOG = (["columnas_faltantes", "fecha_paquete", "comercios_descartados"] + [c.nombre for c in CONTROLES]
             + ["portal_actualizado"])


@dataclass
class ResultadoControl:
    fecha: date
    control: str
    resultado: str  # ok | advertencia | error
    valor: float | None
    detalle: str


class ErrorCalidad(Exception):
    """Algún control dio error grave: el día no se guarda."""

    def __init__(self, fecha: date, errores: list[ResultadoControl]):
        self.fecha = fecha
        self.errores = errores
        resumen = "; ".join(f"{e.control}: {e.detalle}" for e in errores)
        super().__init__(f"Controles de calidad fallidos para {fecha}: {resumen}")


# --------------------------------------------------------------------------- controles

def _medir(control: Control, valor, total) -> float | None:
    if valor is None:
        return None
    if control.medida == "porcentaje":
        return 100.0 * float(valor) / float(total) if total else 0.0
    if control.medida == "caida":
        return -float(valor)
    return float(valor)


def _gravedad(control: Control, medida: float | None) -> str:
    if medida is None:
        return OK
    if control.error is not None and medida > control.error:
        return ERROR
    if control.advertencia is not None and medida > control.advertencia:
        return ADVERTENCIA
    return OK


def cargar_dia_anterior(con: duckdb.DuckDBPyConnection, fecha: date, dir_datos: Path | None = None) -> date | None:
    """Crea precios_anteriores y comercios_anteriores con el último día guardado anterior a `fecha`.

    Si no hay ninguno, las crea vacías (los controles que comparan contra el día anterior no avisan nada).
    Devuelve la fecha del día anterior que se usó, o None.
    """
    dir_datos = dir_datos or DIR_DATOS
    guardadas = []
    for carpeta in (dir_datos / "precios").glob("fecha=*"):
        try:
            f = date.fromisoformat(carpeta.name.removeprefix("fecha="))
        except ValueError:  # carpetas temporales de una corrida interrumpida (fecha=...tmp)
            continue
        if f < fecha and (carpeta / "precios.parquet").exists():
            guardadas.append(f)

    if not guardadas:
        con.execute("create or replace table precios_anteriores as select * from precios_dia where false")
        con.execute("create or replace table comercios_anteriores as select * from comercios_dia where false")
        return None

    anterior = max(guardadas)
    for tabla, carpeta in (("precios_anteriores", "precios"), ("comercios_anteriores", "comercios")):
        ruta = dir_datos / carpeta / f"fecha={anterior.isoformat()}" / f"{carpeta}.parquet"
        con.execute(f"create or replace table {tabla} as "
                    f"select * from read_parquet('{ruta.as_posix()}', hive_partitioning=false)")
    return anterior


def _correr_control(con: duckdb.DuckDBPyConnection, control: Control, fecha: date) -> ResultadoControl:
    sql = (DIR_SQL / control.archivo).read_text(encoding="utf-8")
    valor, total, detalle = con.execute(sql).fetchall()[0]
    medida = _medir(control, valor, total)
    if control.medida == "porcentaje" and valor:
        detalle = f"{valor:,} de {total:,}; {detalle}"
    if medida is None:
        detalle = "sin día anterior para comparar"
    return ResultadoControl(fecha, control.nombre, _gravedad(control, medida), medida, detalle)


def controlar_columnas(con: duckdb.DuckDBPyConnection, fecha: date) -> ResultadoControl:
    """Verifica que los CSV traigan las columnas de la especificación. Se corre apenas se leen los CSV,
    antes del SQL de la ingesta (necesita las vistas crudo_comercio, crudo_sucursales y crudo_productos)."""
    return _correr_control(con, CONTROL_COLUMNAS, fecha)


def controlar_datos(con: duckdb.DuckDBPyConnection, fecha: date) -> list[ResultadoControl]:
    """Corre los controles de sql/calidad/. Necesita las tablas de la ingesta y las del día anterior."""
    return [_correr_control(con, control, fecha) for control in CONTROLES]


def controlar_fecha(fecha: date, dia: str, dia_de_la_fecha: str,
                    fecha_esperada: date | None) -> ResultadoControl:
    """La fecha de la carpeta del zip tiene que coincidir con la que informa el portal y con el día del archivo."""
    if fecha_esperada is not None and fecha != fecha_esperada:
        return ResultadoControl(fecha, "fecha_paquete", ERROR, None,
                                f"el zip trae datos del {fecha} y el portal informa {fecha_esperada}")
    if dia != dia_de_la_fecha:
        return ResultadoControl(fecha, "fecha_paquete", ERROR, None,
                                f"el archivo es de un {dia} pero la fecha {fecha} cae un {dia_de_la_fecha}")
    return ResultadoControl(fecha, "fecha_paquete", OK, None, f"{fecha} ({dia})")


def controlar_comercios(fecha: date, descartados: list[str]) -> ResultadoControl:
    """Comercios cuyo zip vino vacío, roto o con datos viejos (se descartan, el resto se guarda)."""
    if not descartados:
        return ResultadoControl(fecha, "comercios_descartados", OK, 0, "-")
    return ResultadoControl(fecha, "comercios_descartados", ADVERTENCIA, len(descartados), " | ".join(descartados))


def controlar_portal(hoy: date, fecha_mas_reciente: date) -> ResultadoControl:
    """El portal tiene que haber publicado datos de hoy o de ayer."""
    dias = (hoy - fecha_mas_reciente).days
    detalle = f"último paquete publicado: {fecha_mas_reciente}, hoy: {hoy}"
    return ResultadoControl(hoy, "portal_actualizado", ERROR if dias > MAX_DIAS_PORTAL else OK, dias, detalle)


# --------------------------------------------------------------------------- log

def registrar(resultados: list[ResultadoControl], ruta: Path | None = None) -> None:
    """Agrega los resultados a data/calidad/log_calidad.csv.

    Es idempotente: si ya hay una fila con la misma fecha y control, la reemplaza.
    """
    ruta = ruta or RUTA_LOG
    columnas = ["fecha", "control", "resultado", "valor", "detalle"]
    nuevas = {(r.fecha.isoformat(), r.control) for r in resultados}

    filas = []
    if ruta.exists():
        with open(ruta, encoding="utf-8", newline="") as f:
            filas = [r for r in csv.DictReader(f) if (r["fecha"], r["control"]) not in nuevas]
    for r in resultados:
        filas.append({
            "fecha": r.fecha.isoformat(),
            "control": r.control,
            "resultado": r.resultado,
            "valor": "" if r.valor is None else round(r.valor, 3),
            "detalle": r.detalle,
        })

    def clave(fila):
        orden = ORDEN_LOG.index(fila["control"]) if fila["control"] in ORDEN_LOG else len(ORDEN_LOG)
        return fila["fecha"], orden

    filas.sort(key=clave)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(filas)
