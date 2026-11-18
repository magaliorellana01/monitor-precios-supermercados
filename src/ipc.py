"""Descarga la inflación mensual oficial (IPC del INDEC) desde la API de ArgentinaDatos.

    python -m src.ipc

Guarda data/externos/ipc.csv con una fila por mes: `fecha` (último día del mes) y `variacion_mensual_pct`.
Se usa en el análisis para comparar el índice propio de la canasta con la inflación oficial.
"""

from __future__ import annotations

import csv
import json
import logging
import sys
import urllib.request
from pathlib import Path

from . import ingesta

URL = "https://api.argentinadatos.com/v1/finanzas/indices/inflacion"
RUTA = ingesta.DIR_DATOS / "externos" / "ipc.csv"

log = logging.getLogger("ipc")


def parsear(respuesta: list[dict]) -> list[tuple[str, float]]:
    """Convierte la respuesta de la API en filas (fecha, variación mensual en %), ordenadas por fecha."""
    filas = [(r["fecha"], float(r["valor"])) for r in respuesta if r.get("valor") is not None]
    return sorted(filas)


def descargar(url: str = URL, timeout: int = 30) -> list[tuple[str, float]]:
    pedido = urllib.request.Request(url, headers={"User-Agent": "monitor-precios-supermercados"})
    with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
        return parsear(json.load(respuesta))


def guardar(filas: list[tuple[str, float]], ruta: Path = RUTA) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(["fecha", "variacion_mensual_pct"])
        escritor.writerows(filas)
    return ruta


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        filas = descargar()
    except (OSError, ValueError, KeyError) as e:
        log.error("No se pudo descargar el IPC: %s", e)
        return 1
    if not filas:
        log.error("La API no devolvió datos de inflación")
        return 1
    ruta = guardar(filas)
    log.info("IPC guardado en %s (%d meses, último: %s = %s%%)", ruta, len(filas), *filas[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
