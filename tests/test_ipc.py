"""Tests de la descarga del IPC (sin red: se prueba el parseo y el guardado)."""

from __future__ import annotations

import csv

from src import ipc


def test_parsear_ordena_y_descarta_valores_vacios():
    respuesta = [
        {"fecha": "2026-02-28", "valor": 2.9},
        {"fecha": "2026-01-31", "valor": 3.1},
        {"fecha": "2026-03-31", "valor": None},
    ]
    assert ipc.parsear(respuesta) == [("2026-01-31", 3.1), ("2026-02-28", 2.9)]


def test_guardar_escribe_encabezado_y_filas(tmp_path):
    ruta = ipc.guardar([("2026-01-31", 3.1), ("2026-02-28", 2.9)], tmp_path / "externos" / "ipc.csv")
    with ruta.open(encoding="utf-8") as f:
        filas = list(csv.reader(f))
    assert filas == [["fecha", "variacion_mensual_pct"], ["2026-01-31", "3.1"], ["2026-02-28", "2.9"]]


def test_main_devuelve_1_si_falla_la_descarga(monkeypatch):
    def falla(*a, **k):
        raise OSError("sin conexión")

    monkeypatch.setattr(ipc, "descargar", falla)
    assert ipc.main() == 1
