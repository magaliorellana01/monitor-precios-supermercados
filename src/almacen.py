"""Almacén de los datos diarios en Releases de GitHub (ver docs/decisiones.md, decisión 5).

Los Parquet diarios no van en git: cada día pesa ~17 MB. Se guardan como archivos adjuntos de un
Release por mes (`datos-AAAA-MM`), con un archivo por tabla y día: `precios_2026-11-18.parquet`.

Uso (requiere la CLI `gh` instalada y autenticada; en GitHub Actions ya viene lista):
    python -m src.almacen bajar --dias 10    # baja los últimos días que no estén en data/
    python -m src.almacen subir              # sube los días de data/ que falten en los Releases
    python -m src.almacen subir --forzar     # reemplaza lo ya subido (por ejemplo, tras reprocesar un día)
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from . import ingesta

TABLAS = tuple(ingesta.TABLAS.values())  # precios, sucursales, comercios, productos

log = logging.getLogger("almacen")


class ErrorGh(RuntimeError):
    """Un comando de la CLI `gh` terminó con error."""

    def __init__(self, argumentos: tuple, codigo: int, salida: str):
        self.salida = salida
        super().__init__(f"gh {' '.join(argumentos[:3])} terminó con código {codigo}: {salida.strip()}")


def gh(*argumentos: str) -> str:
    """Corre la CLI de GitHub y devuelve lo que imprimió. Los tests reemplazan esta función."""
    r = subprocess.run(["gh", *argumentos], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise ErrorGh(argumentos, r.returncode, r.stderr or r.stdout)
    return r.stdout


# --------------------------------------------------------------------------- nombres

def etiqueta(fecha: date) -> str:
    """Un Release por mes, para no pasar el máximo de 1000 archivos por Release (4 tablas x 31 días = 124)."""
    return f"datos-{fecha:%Y-%m}"


def nombre_archivo(tabla: str, fecha: date) -> str:
    return f"{tabla}_{fecha.isoformat()}.parquet"


def ruta_local(tabla: str, fecha: date) -> Path:
    return ingesta.DIR_DATOS / tabla / f"fecha={fecha.isoformat()}" / f"{tabla}.parquet"


def fechas_locales() -> list[date]:
    """Fechas guardadas en data/ con las cuatro tablas completas."""
    fechas = []
    for carpeta in (ingesta.DIR_DATOS / "precios").glob("fecha=*"):
        try:
            fecha = date.fromisoformat(carpeta.name.removeprefix("fecha="))
        except ValueError:  # carpetas temporales de una corrida interrumpida (fecha=...tmp)
            continue
        if all(ruta_local(t, fecha).exists() for t in TABLAS):
            fechas.append(fecha)
    return sorted(fechas)


def archivos_del_release(tag: str) -> set[str] | None:
    """Nombres de los archivos de un Release, o None si el Release todavía no existe."""
    try:
        salida = gh("release", "view", tag, "--json", "assets")
    except ErrorGh as e:
        if "not found" in e.salida.lower():
            return None
        raise
    return {a["name"] for a in json.loads(salida)["assets"]}


# --------------------------------------------------------------------------- subir

def subir(forzar: bool = False) -> int:
    """Sube al Release del mes los días de data/ que todavía no estén. Devuelve cuántos días subió."""
    subidos = 0
    por_mes: dict[str, list[date]] = {}
    for fecha in fechas_locales():
        por_mes.setdefault(etiqueta(fecha), []).append(fecha)

    for tag, fechas in por_mes.items():
        existentes = archivos_del_release(tag)
        if existentes is None:
            log.info("Creando el Release %s", tag)
            gh("release", "create", tag, "--title", f"Datos {tag.removeprefix('datos-')}",
               "--notes", "Parquet diarios de precios SEPA (CABA + GBA). Ver docs/fuente_sepa.md.",
               "--latest=false")
            existentes = set()

        for fecha in fechas:
            faltan = [t for t in TABLAS if nombre_archivo(t, fecha) not in existentes]
            if not faltan and not forzar:
                continue
            with tempfile.TemporaryDirectory(prefix="almacen_") as tmp:
                # gh sube el archivo con su nombre de origen: se copia con el nombre que lleva en el Release
                archivos = []
                for tabla in TABLAS:
                    destino = Path(tmp) / nombre_archivo(tabla, fecha)
                    shutil.copyfile(ruta_local(tabla, fecha), destino)
                    archivos.append(str(destino))
                gh("release", "upload", tag, *archivos, "--clobber")
            log.info("Subido %s al Release %s", fecha, tag)
            subidos += 1
    if not subidos:
        log.info("No hay días nuevos para subir")
    return subidos


# --------------------------------------------------------------------------- bajar

def bajar(dias: int, hoy: date | None = None) -> int:
    """Baja de los Releases los últimos `dias` días que no estén en data/. Devuelve cuántos días bajó.

    Hace falta para que la ingesta sepa qué días ya están guardados y pueda comparar contra el día anterior.
    """
    hoy = hoy or datetime.now(ingesta.HUSO_ARGENTINA).date()
    desde = hoy - timedelta(days=dias)
    locales = set(fechas_locales())

    # los meses que cubre la ventana (puede ser el actual y el anterior)
    meses = {etiqueta(desde + timedelta(days=i)) for i in range((hoy - desde).days + 1)}

    bajados = 0
    for tag in sorted(meses):
        existentes = archivos_del_release(tag)
        if existentes is None:
            log.info("El Release %s todavía no existe", tag)
            continue

        pendientes = []
        for tabla_y_fecha in existentes:
            tabla, _, resto = tabla_y_fecha.partition("_")
            try:
                fecha = date.fromisoformat(resto.removesuffix(".parquet"))
            except ValueError:
                continue
            if tabla in TABLAS and desde <= fecha <= hoy and fecha not in locales:
                pendientes.append((tabla, fecha))

        # solo los días que tienen las cuatro tablas
        completas = {f for _, f in pendientes if all(nombre_archivo(t, f) in existentes for t in TABLAS)}
        if not completas:
            continue

        with tempfile.TemporaryDirectory(prefix="almacen_") as tmp:
            patrones = []
            for fecha in sorted(completas):
                for tabla in TABLAS:
                    patrones += ["--pattern", nombre_archivo(tabla, fecha)]
            gh("release", "download", tag, "--dir", tmp, *patrones)
            for fecha in sorted(completas):
                for tabla in TABLAS:
                    destino = ruta_local(tabla, fecha)
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(Path(tmp) / nombre_archivo(tabla, fecha), destino)
                log.info("Bajado %s desde el Release %s", fecha, tag)
                bajados += 1
    if not bajados:
        log.info("No hay días para bajar")
    return bajados


# --------------------------------------------------------------------------- línea de comandos

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="orden", required=True)
    p_bajar = sub.add_parser("bajar", help="baja los últimos días guardados en los Releases")
    p_bajar.add_argument("--dias", type=int, default=10, help="cuántos días hacia atrás (por defecto 10)")
    p_subir = sub.add_parser("subir", help="sube a los Releases los días que falten")
    p_subir.add_argument("--forzar", action="store_true", help="reemplazar lo que ya está subido")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)
    try:
        if args.orden == "bajar":
            bajar(args.dias)
        else:
            subir(args.forzar)
    except (ErrorGh, FileNotFoundError) as e:
        log.error("No se pudo usar la CLI de GitHub (¿está instalada y autenticada? `gh auth login`): %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
