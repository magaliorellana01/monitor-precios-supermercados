"""Ingesta diaria de la base SEPA (Precios Claros).

Descarga los paquetes publicados, los filtra por zona (CABA + GBA) y los guarda en Parquet
particionado por fecha. Es idempotente: si una fecha ya está guardada, no la vuelve a procesar.

Uso:
    python -m src.ingesta                       # procesa los paquetes disponibles que falten (hasta 7 días)
    python -m src.ingesta --dia lunes           # solo el paquete de ese día de la semana
    python -m src.ingesta --archivo x.zip       # un zip ya descargado (no descarga nada)
    python -m src.ingesta --forzar              # reprocesa aunque la fecha ya esté guardada

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
from datetime import date, datetime
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATOS = RAIZ / "data"
DIR_SQL = RAIZ / "sql" / "ingesta"
LOG_INGESTA = DIR_DATOS / "ingesta" / "log_ingesta.csv"

API_CKAN = "https://datos.produccion.gob.ar/api/3/action/package_show?id=sepa-precios"
USER_AGENT = "monitor-precios-supermercados/0.1"
DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

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
                "filas_leidas", "filas_guardadas", "sucursales_zona", "banderas_zona",
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

def procesar_zip(zip_externo: Path, dia: str, forzar: bool = False) -> Resultado | None:
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
        correr_sql(con)

        resultado.filas_leidas = escalar(
            con, "select count(*) from crudo_productos where regexp_full_match(id_comercio, '[0-9]+')")
        resultado.filas_guardadas = escalar(con, "select count(*) from precios_dia")
        resultado.sucursales_zona = escalar(con, "select count(*) from sucursales_dia")
        resultado.banderas_zona = escalar(
            con, "select count(distinct (id_comercio, id_bandera)) from precios_dia")
        resultado.productos_zona = escalar(con, "select count(distinct id_producto) from precios_dia")
        resultado.mb_parquet = guardar(con, fecha)
        con.close()

    resultado.segundos = time.perf_counter() - inicio
    registrar(resultado)
    log.info(
        "%s (%s): %s filas leídas, %s guardadas | %d sucursales y %d banderas en la zona | "
        "%s productos | %.1f MB | %d comercios descartados | %.0f s",
        fecha, dia, f"{resultado.filas_leidas:,}", f"{resultado.filas_guardadas:,}",
        resultado.sucursales_zona, resultado.banderas_zona, f"{resultado.productos_zona:,}",
        resultado.mb_parquet, len(resultado.comercios_descartados), resultado.segundos,
    )
    return resultado


def procesar_paquete(paquete: Paquete, forzar: bool = False) -> Resultado | None:
    if paquete.fecha_estimada and ya_guardada(paquete.fecha_estimada) and not forzar:
        log.info("%s (%s) ya está guardada, no se descarga", paquete.fecha_estimada, paquete.dia)
        return None
    with tempfile.TemporaryDirectory(prefix="sepa_zip_") as tmp:
        zip_externo = Path(tmp) / f"sepa_{paquete.dia}.zip"
        log.info("Descargando %s (fecha estimada %s)...", zip_externo.name, paquete.fecha_estimada)
        descargar(paquete.url, zip_externo)
        return procesar_zip(zip_externo, paquete.dia, forzar)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--dia", choices=DIAS_SEMANA, help="procesar solo el paquete de este día de la semana")
    grupo.add_argument("--archivo", type=Path, help="procesar un zip ya descargado")
    parser.add_argument("--forzar", action="store_true", help="reprocesar aunque la fecha ya esté guardada")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)
    sys.stdout.reconfigure(encoding="utf-8")

    if args.archivo:
        dia = DIAS_SEMANA[fecha_del_paquete(args.archivo).weekday()]
        procesar_zip(args.archivo, dia, args.forzar)
        return 0

    paquetes = listar_paquetes()
    if args.dia:
        paquetes = [p for p in paquetes if p.dia == args.dia]

    errores = 0
    for paquete in paquetes:
        try:
            procesar_paquete(paquete, args.forzar)
        except Exception:
            errores += 1
            log.exception("Error procesando el paquete del %s", paquete.dia)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
