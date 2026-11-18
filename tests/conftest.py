import itertools
from datetime import date

import duckdb
import pytest

from src import calidad, ingesta
from tests.ayudas import escribir_carpetas

FECHA = date(2026, 11, 16)  # un lunes


@pytest.fixture
def datos_temporales(monkeypatch, tmp_path):
    """Manda todo lo que escriben la ingesta y los controles a una carpeta temporal."""
    datos = tmp_path / "data"
    monkeypatch.setattr(ingesta, "DIR_DATOS", datos)
    monkeypatch.setattr(ingesta, "LOG_INGESTA", datos / "ingesta" / "log_ingesta.csv")
    monkeypatch.setattr(calidad, "DIR_DATOS", datos)
    monkeypatch.setattr(calidad, "RUTA_LOG", datos / "calidad" / "log_calidad.csv")
    return datos


@pytest.fixture
def cargar(tmp_path):
    """Devuelve una función que arma los comercios, los lee y corre el SQL de la ingesta."""
    contador = itertools.count()

    def _cargar(comercios):
        carpetas = escribir_carpetas(tmp_path / f"crudo{next(contador)}", comercios)
        con = duckdb.connect()
        ingesta.crear_vistas_crudas(con, carpetas)
        ingesta.correr_sql(con)
        return con

    return _cargar


@pytest.fixture
def controlar(tmp_path):
    """Devuelve una función que corre los controles de datos y los entrega por nombre.

    Si el test no armó las tablas del día anterior, se crean vacías.
    """

    def _controlar(con, con_anterior: bool = False):
        if not con_anterior:
            calidad.cargar_dia_anterior(con, FECHA, tmp_path / "sin_datos")
        return {r.control: r for r in calidad.controlar_datos(con, FECHA)}

    return _controlar
