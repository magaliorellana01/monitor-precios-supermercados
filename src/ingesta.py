"""Ingesta diaria de la base SEPA (Precios Claros).

Descarga los paquetes publicados, los filtra por zona (CABA + GBA) y los guarda en Parquet
particionado por fecha. Es idempotente: si una fecha ya está guardada, no la vuelve a procesar.

Uso:
    python -m src.ingesta                       # procesa los paquetes disponibles que falten (hasta 7 días)
    python -m src.ingesta --dia lunes           # solo el paquete de ese día de la semana
    python -m src.ingesta --archivo x.zip       # un zip ya descargado (no descarga nada)
    python -m src.ingesta --forzar              # reprocesa aunque la fecha ya esté guardada
    python -m src.ingesta --aceptar-errores     # guarda el día aunque los controles de calidad den error
    python -m src.ingesta --verificar-acceso    # solo prueba que se pueda llegar al portal

Antes de guardar cada día se corren los controles de src/calidad.py. Si alguno da error grave,
ese día no se guarda y el proceso termina con código de salida 1.

La estructura de la fuente está documentada en docs/fuente_sepa.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import shutil
import sys
import tempfile
import time
import unicodedata
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from . import calidad

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATOS = RAIZ / "data"
DIR_SQL = RAIZ / "sql" / "ingesta"
LOG_INGESTA = DIR_DATOS / "ingesta" / "log_ingesta.csv"

API_CKAN = "https://datos.produccion.gob.ar/api/3/action/package_show?id=sepa-precios"
USER_AGENT = "monitor-precios-supermercados/0.1"
DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
HUSO_ARGENTINA = timezone(timedelta(hours=-3))  # Argentina no usa horario de verano

# Un comercio cuyos CSV tienen más de esta cantidad de días de diferencia con la fecha del
# paquete se descarta ese día (ver docs/decisiones.md, decisión 2).
MAX_DIAS_DESFASE = 2

# Tablas que se guardan: nombre de la tabla en SQL -> carpeta en data/
TABLAS = {
    "precios_dia": "precios",
    "sucursales_dia": "sucursales",
    "comercios_dia": "comercios",
    "productos_dia": "productos",
}

log = logging.getLogger("ingesta")


@dataclass
class Paquete:
    """Un zip diario publicado en el portal."""

    dia: str
    url: str
    fecha_estimada: date | None  # según la API; la fecha válida se lee adentro del zip


@dataclass
class Resultado:
    fecha: date
    dia: str
    comercios_en_paquete: int = 0
    comercios_descartados: list[str] = field(default_factory=list)
    filas_leidas: int = 0
    filas_guardadas: int = 0
    filas_descartadas: int = 0
    sucursales_zona: int = 0
    banderas_zona: int = 0
    productos_zona: int = 0
    mb_parquet: float = 0.0
    segundos: float = 0.0


# --------------------------------------------------------------------------- descarga

def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def listar_paquetes() -> list[Paquete]:
    """Consulta la API CKAN y devuelve los 7 zips diarios con su fecha estimada."""
    pedido = urllib.request.Request(API_CKAN, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(pedido, timeout=60) as r:
        recursos = json.load(r)["result"]["resources"]

    paquetes = []
    for rec in recursos:
        dia = _sin_acentos(rec["name"]).strip().lower()
        if dia not in DIAS_SEMANA:
            continue
        modificado = rec.get("last_modified") or rec.get("created")
        fecha = datetime.fromisoformat(modificado).date() if modificado else None
        paquetes.append(Paquete(dia=dia, url=rec["url"], fecha_estimada=fecha))
    return sorted(paquetes, key=lambda p: p.fecha_estimada or date.min)


def descargar(url: str, destino: Path, intentos: int = 3) -> None:
    for intento in range(1, intentos + 1):
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(pedido, timeout=300) as r, open(destino, "wb") as f:
                shutil.copyfileobj(r, f, length=1 << 20)
            return
        except OSError as e:
            if intento == intentos:
                raise
            log.warning("Falló la descarga (intento %d/%d): %s. Reintentando...", intento, intentos, e)
            time.sleep(10 * intento)


# --------------------------------------------------------------------------- lectura del zip

def fecha_del_paquete(zip_externo: Path) -> date:
    """La fecha válida es la de la carpeta interna del zip (AAAA-MM-DD/)."""
    with zipfile.ZipFile(zip_externo) as z:
        carpetas = {n.split("/")[0] for n in z.namelist() if "/" in n}
    if len(carpetas) != 1:
        raise ValueError(f"Se esperaba una sola carpeta de fecha en el zip y hay {sorted(carpetas)}")
    return date.fromisoformat(carpetas.pop())


def extraer_comercios(zip_externo: Path, fecha: date, destino: Path, resultado: Resultado) -> list[Path]:
    """Extrae el zip de cada comercio en su propia carpeta. Descarta los rotos o desactualizados."""
    carpetas = []
    with zipfile.ZipFile(zip_externo) as z:
        internos = [i for i in z.infolist() if i.filename.endswith(".zip")]
        resultado.comercios_en_paquete = len(internos)
        for info in internos:
            nombre = Path(info.filename).stem
            try:
                with z.open(info) as f, zipfile.ZipFile(f) as zi:
                    archivos = {Path(n).name for n in zi.namelist()}
                    faltan = {"comercio.csv", "sucursales.csv", "productos.csv"} - archivos
                    if faltan:
                        raise ValueError(f"faltan {sorted(faltan)}")
                    fecha_csv = max(date(*i.date_time[:3]) for i in zi.infolist())
                    desfase = (fecha - fecha_csv).days
                    if desfase > MAX_DIAS_DESFASE:
                        raise ValueError(f"datos desactualizados (CSV del {fecha_csv})")
                    carpeta = destino / nombre
                    zi.extractall(carpeta)
            except (zipfile.BadZipFile, ValueError) as e:
                motivo = "zip vacío o roto" if isinstance(e, zipfile.BadZipFile) else str(e)
                log.warning("Comercio descartado: %s (%s)", nombre, motivo)
                resultado.comercios_descartados.append(f"{nombre}: {motivo}")
                continue
            carpetas.append(carpeta)
    return carpetas


# --------------------------------------------------------------------------- transformación

def _lista_sql(rutas: list[Path]) -> str:
    return "[" + ", ".join("'" + r.as_posix().replace("'", "''") + "'" for r in rutas) + "]"


def crear_vistas_crudas(con: duckdb.DuckDBPyConnection, carpetas: list[Path]) -> None:
    for tabla in ["comercio", "sucursales", "productos"]:
        archivos = _lista_sql([c / f"{tabla}.csv" for c in carpetas])
        con.execute(f"""
            create or replace view crudo_{tabla} as
            select * from read_csv({archivos}, delim='|', header=true, all_varchar=true,
                                   null_padding=true, quote='"', escape='"')
        """)


def correr_sql(con: duckdb.DuckDBPyConnection) -> None:
    for archivo in sorted(DIR_SQL.glob("*.sql")):
        con.execute(archivo.read_text(encoding="utf-8"))


def escalar(con: duckdb.DuckDBPyConnection, consulta: str):
    return con.execute(consulta).fetchall()[0][0]


# --------------------------------------------------------------------------- guardado

def ruta_particion(carpeta: str, fecha: date) -> Path:
    return DIR_DATOS / carpeta / f"fecha={fecha.isoformat()}"


def ya_guardada(fecha: date) -> bool:
    return all((ruta_particion(c, fecha) / f"{c}.parquet").exists() for c in TABLAS.values())


def guardar(con: duckdb.DuckDBPyConnection, fecha: date) -> float:
    """Escribe cada tabla en una carpeta temporal y después la mueve: si algo falla a mitad de
    camino no queda una partición a medias, y si se corre dos veces se reemplaza (no se duplica)."""
    mb = 0.0
    for tabla, carpeta in TABLAS.items():
        final = ruta_particion(carpeta, fecha)
        temporal = final.with_name(final.name + ".tmp")
        shutil.rmtree(temporal, ignore_errors=True)
        temporal.mkdir(parents=True)
        archivo = temporal / f"{carpeta}.parquet"
        con.execute(f"copy {tabla} to '{archivo.as_posix()}' (format parquet, compression zstd)")
        mb += archivo.stat().st_size / 1e6
        shutil.rmtree(final, ignore_errors=True)
        temporal.rename(final)
    return mb


def registrar(resultado: Resultado) -> None:
    """Agrega (o reemplaza) la fila de esta fecha en data/ingesta/log_ingesta.csv."""
    columnas = ["fecha", "dia", "ejecutado", "comercios_en_paquete", "comercios_descartados",
                "filas_leidas", "filas_guardadas", "filas_descartadas", "sucursales_zona", "banderas_zona",
                "productos_zona", "mb_parquet", "segundos"]
    filas = []
    if LOG_INGESTA.exists():
        with open(LOG_INGESTA, encoding="utf-8", newline="") as f:
            filas = [r for r in csv.DictReader(f) if r["fecha"] != resultado.fecha.isoformat()]
    filas.append({
        "fecha": resultado.fecha.isoformat(),
        "dia": resultado.dia,
        "ejecutado": datetime.now().isoformat(timespec="seconds"),
        "comercios_en_paquete": resultado.comercios_en_paquete,
        "comercios_descartados": " | ".join(resultado.comercios_descartados),
        "filas_leidas": resultado.filas_leidas,
        "filas_guardadas": resultado.filas_guardadas,
        "filas_descartadas": resultado.filas_descartadas,
        "sucursales_zona": resultado.sucursales_zona,
        "banderas_zona": resultado.banderas_zona,
        "productos_zona": resultado.productos_zona,
        "mb_parquet": round(resultado.mb_parquet, 2),
        "segundos": round(resultado.segundos, 1),
    })
    filas.sort(key=lambda r: r["fecha"])
    LOG_INGESTA.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_INGESTA, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(filas)


# --------------------------------------------------------------------------- orquestación

def correr_controles(con: duckdb.DuckDBPyConnection, fecha: date, dia: str, fecha_esperada: date | None,
                     resultado: Resultado, previos: list[calidad.ResultadoControl]) -> list[calidad.ResultadoControl]:
    """Corre todos los controles de calidad del día, los registra en el log y los informa.
    `previos` son los controles que ya se corrieron antes del SQL (las columnas)."""
    calidad.cargar_dia_anterior(con, fecha, DIR_DATOS)
    resultados = [
        *previos,
        calidad.controlar_fecha(fecha, dia, DIAS_SEMANA[fecha.weekday()], fecha_esperada),
        calidad.controlar_comercios(fecha, resultado.comercios_descartados),
        *calidad.controlar_datos(con, fecha),
    ]
    calidad.registrar(resultados)

    niveles = {calidad.ERROR: logging.ERROR, calidad.ADVERTENCIA: logging.WARNING}
    for r in resultados:
        if r.resultado != calidad.OK:
            log.log(niveles[r.resultado], "Control %s: %s (%s)", r.resultado.upper(), r.control, r.detalle)
    return resultados


def procesar_zip(zip_externo: Path, dia: str, forzar: bool = False, fecha_esperada: date | None = None,
                 aceptar_errores: bool = False) -> Resultado | None:
    """Procesa un zip diario. Si algún control de calidad da error grave y no se pidió
    `aceptar_errores`, el día no se guarda y se levanta calidad.ErrorCalidad."""
    inicio = time.perf_counter()
    fecha = fecha_del_paquete(zip_externo)
    if ya_guardada(fecha) and not forzar:
        log.info("%s ya está guardada, se saltea (usar --forzar para reprocesar)", fecha)
        return None

    resultado = Resultado(fecha=fecha, dia=dia)
    with tempfile.TemporaryDirectory(prefix="sepa_") as tmp:
        carpetas = extraer_comercios(zip_externo, fecha, Path(tmp), resultado)
        if not carpetas:
            raise RuntimeError(f"El paquete del {fecha} no trae ningún comercio válido")

        con = duckdb.connect()
        crear_vistas_crudas(con, carpetas)

        columnas = calidad.controlar_columnas(con, fecha)
        if columnas.resultado == calidad.ERROR:  # sin las columnas no se puede seguir, ni con --aceptar-errores
            log.error("Control ERROR: %s (%s)", columnas.control, columnas.detalle)
            calidad.registrar([columnas])
            con.close()
            raise calidad.ErrorCalidad(fecha, [columnas])

        correr_sql(con)

        resultado.filas_leidas = escalar(
            con, "select count(*) from crudo_productos where regexp_full_match(id_comercio, '[0-9]+')")
        resultado.filas_guardadas = escalar(con, "select count(*) from precios_dia")
        resultado.filas_descartadas = escalar(
            con, "select count(*) from precios_marcados_dia where motivo_descarte is not null")
        resultado.sucursales_zona = escalar(con, "select count(*) from sucursales_dia")
        resultado.banderas_zona = escalar(
            con, "select count(distinct (id_comercio, id_bandera)) from precios_dia")
        resultado.productos_zona = escalar(con, "select count(distinct id_producto) from precios_dia")

        controles = correr_controles(con, fecha, dia, fecha_esperada, resultado, [columnas])
        errores = [c for c in controles if c.resultado == calidad.ERROR]
        if errores and not aceptar_errores:
            con.close()
            raise calidad.ErrorCalidad(fecha, errores)
        if errores:
            log.warning("Se guarda %s aunque hay %d controles con error (--aceptar-errores)", fecha, len(errores))

        resultado.mb_parquet = guardar(con, fecha)
        con.close()

    resultado.segundos = time.perf_counter() - inicio
    registrar(resultado)
    log.info(
        "%s (%s): %s filas leídas, %s guardadas y %s descartadas | %d sucursales y %d banderas en la zona | "
        "%s productos | %.1f MB | %d comercios descartados | %.0f s",
        fecha, dia, f"{resultado.filas_leidas:,}", f"{resultado.filas_guardadas:,}",
        f"{resultado.filas_descartadas:,}", resultado.sucursales_zona, resultado.banderas_zona,
        f"{resultado.productos_zona:,}", resultado.mb_parquet, len(resultado.comercios_descartados),
        resultado.segundos,
    )
    return resultado


def procesar_paquete(paquete: Paquete, forzar: bool = False, aceptar_errores: bool = False) -> Resultado | None:
    if paquete.fecha_estimada and ya_guardada(paquete.fecha_estimada) and not forzar:
        log.info("%s (%s) ya está guardada, no se descarga", paquete.fecha_estimada, paquete.dia)
        return None
    with tempfile.TemporaryDirectory(prefix="sepa_zip_") as tmp:
        zip_externo = Path(tmp) / f"sepa_{paquete.dia}.zip"
        log.info("Descargando %s (fecha estimada %s)...", zip_externo.name, paquete.fecha_estimada)
        descargar(paquete.url, zip_externo)
        return procesar_zip(zip_externo, paquete.dia, forzar, paquete.fecha_estimada, aceptar_errores)


def controlar_portal(paquetes: list[Paquete]) -> bool:
    """Verifica que el portal haya publicado datos de hoy o de ayer. Devuelve False si está desactualizado."""
    fechas = [p.fecha_estimada for p in paquetes if p.fecha_estimada]
    if not fechas:
        return True
    resultado = calidad.controlar_portal(datetime.now(HUSO_ARGENTINA).date(), max(fechas))
    calidad.registrar([resultado])
    if resultado.resultado == calidad.ERROR:
        log.error("Control ERROR: portal_actualizado (%s)", resultado.detalle)
        return False
    return True


def verificar_acceso() -> bool:
    """Prueba que se pueda llegar al portal: consulta la API y pide los primeros bytes del último zip.

    Sirve para saber, desde GitHub Actions, si el servidor bloquea las IP del exterior (docs/fuente_sepa.md).
    """
    try:
        inicio = time.perf_counter()
        paquetes = listar_paquetes()
        log.info("API del portal: OK (%d paquetes, %.1f s)", len(paquetes), time.perf_counter() - inicio)
        ultimo = paquetes[-1]
        pedido = urllib.request.Request(ultimo.url, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-1023"})
        inicio = time.perf_counter()
        with urllib.request.urlopen(pedido, timeout=60) as r:
            inicio_archivo = r.read(4)
            estado = r.status
        if inicio_archivo[:2] != b"PK":
            log.error("El servidor respondió (HTTP %s) pero no entregó un zip", estado)
            return False
        log.info("Descarga de sepa_%s (%s): OK (HTTP %s, %.1f s)", ultimo.dia, ultimo.fecha_estimada,
                 estado, time.perf_counter() - inicio)
        return True
    except OSError as e:  # incluye errores HTTP (403, 429...), de conexión y de tiempo de espera
        log.error("No se pudo acceder al portal: %s", e)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verificar-acceso", action="store_true",
                        help="solo probar que se puede acceder al portal; no descarga ni guarda nada")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--dia", choices=DIAS_SEMANA, help="procesar solo el paquete de este día de la semana")
    grupo.add_argument("--archivo", type=Path, help="procesar un zip ya descargado")
    parser.add_argument("--forzar", action="store_true", help="reprocesar aunque la fecha ya esté guardada")
    parser.add_argument("--aceptar-errores", action="store_true",
                        help="guardar el día aunque los controles de calidad den error grave")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.verificar_acceso:
        return 0 if verificar_acceso() else 1

    if args.archivo:
        try:
            dia = DIAS_SEMANA[fecha_del_paquete(args.archivo).weekday()]
            procesar_zip(args.archivo, dia, args.forzar, aceptar_errores=args.aceptar_errores)
        except Exception:
            log.exception("Error procesando %s", args.archivo)
            return 1
        return 0

    paquetes = listar_paquetes()
    errores = 0
    if not controlar_portal(paquetes):
        errores += 1
    if args.dia:
        paquetes = [p for p in paquetes if p.dia == args.dia]

    for paquete in paquetes:
        try:
            procesar_paquete(paquete, args.forzar, args.aceptar_errores)
        except calidad.ErrorCalidad as e:
            errores += 1
            log.error("No se guardó el %s: %s", e.fecha, e)
        except Exception:
            errores += 1
            log.exception("Error procesando el paquete del %s", paquete.dia)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
