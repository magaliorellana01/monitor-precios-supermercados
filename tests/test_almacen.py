"""Tests del almacén en Releases. La CLI `gh` se reemplaza por una simulación en memoria."""

from __future__ import annotations

import fnmatch
import json
from datetime import date
from pathlib import Path

import pytest

from src import almacen, ingesta
from tests.ayudas import comercio, productos_en


class GhFalso:
    """Simula los Releases de GitHub: un diccionario de etiqueta -> {nombre de archivo: contenido}."""

    def __init__(self):
        self.releases: dict[str, dict[str, bytes]] = {}
        self.llamadas: list[tuple] = []

    def __call__(self, *args: str) -> str:
        self.llamadas.append(args)
        _, orden, tag, *resto = args
        if orden == "view":
            if tag not in self.releases:
                raise almacen.ErrorGh(args, 1, "release not found")
            return json.dumps({"assets": [{"name": n} for n in self.releases[tag]]})
        if orden == "create":
            self.releases[tag] = {}
            return ""
        if orden == "upload":
            for ruta in resto[:-1]:  # el último argumento es --clobber
                self.releases[tag][Path(ruta).name] = Path(ruta).read_bytes()
            return ""
        if orden == "download":
            carpeta = Path(resto[resto.index("--dir") + 1])
            patrones = [resto[i + 1] for i, a in enumerate(resto) if a == "--pattern"]
            for nombre, contenido in self.releases[tag].items():
                if any(fnmatch.fnmatch(nombre, p) for p in patrones):
                    (carpeta / nombre).write_bytes(contenido)
            return ""
        raise AssertionError(f"llamada inesperada a gh: {args}")

    def subidas(self) -> int:
        return sum(1 for a in self.llamadas if a[1] == "upload")


@pytest.fixture
def gh_falso(monkeypatch):
    falso = GhFalso()
    monkeypatch.setattr(almacen, "gh", falso)
    return falso


@pytest.fixture
def guardar_dias(cargar, datos_temporales):
    """Guarda en data/ las fechas pedidas, con las cuatro tablas."""

    def _guardar(*fechas: date):
        con = cargar([comercio(productos=productos_en("1", 10))])
        for fecha in fechas:
            ingesta.guardar(con, fecha)

    return _guardar


def test_subir_crea_un_release_por_mes_y_sube_las_cuatro_tablas(gh_falso, guardar_dias):
    guardar_dias(date(2026, 11, 17), date(2026, 11, 18), date(2026, 12, 1))

    assert almacen.subir() == 3

    assert set(gh_falso.releases) == {"datos-2026-11", "datos-2026-12"}
    assert sorted(gh_falso.releases["datos-2026-12"]) == [
        "comercios_2026-12-01.parquet", "precios_2026-12-01.parquet",
        "productos_2026-12-01.parquet", "sucursales_2026-12-01.parquet"]
    assert len(gh_falso.releases["datos-2026-11"]) == 8


def test_subir_dos_veces_no_repite_lo_ya_subido(gh_falso, guardar_dias):
    guardar_dias(date(2026, 11, 17), date(2026, 11, 18))
    assert almacen.subir() == 2
    subidas = gh_falso.subidas()

    assert almacen.subir() == 0
    assert gh_falso.subidas() == subidas


def test_subir_completa_un_dia_que_quedo_a_medias(gh_falso, guardar_dias):
    guardar_dias(date(2026, 11, 18))
    almacen.subir()
    del gh_falso.releases["datos-2026-11"]["productos_2026-11-18.parquet"]  # la subida anterior se cortó

    assert almacen.subir() == 1
    assert len(gh_falso.releases["datos-2026-11"]) == 4


def test_subir_con_forzar_reemplaza(gh_falso, guardar_dias):
    guardar_dias(date(2026, 11, 18))
    almacen.subir()
    assert almacen.subir(forzar=True) == 1


def test_bajar_restaura_los_dias_de_la_ventana(gh_falso, guardar_dias, monkeypatch, tmp_path, datos_temporales):
    guardar_dias(date(2026, 11, 1), date(2026, 11, 12), date(2026, 11, 16))
    almacen.subir()
    original = (datos_temporales / "precios" / "fecha=2026-11-16" / "precios.parquet").read_bytes()

    # un runner nuevo: data/ vacía
    monkeypatch.setattr(ingesta, "DIR_DATOS", tmp_path / "runner" / "data")
    assert almacen.bajar(dias=10, hoy=date(2026, 11, 18)) == 2

    assert almacen.fechas_locales() == [date(2026, 11, 12), date(2026, 11, 16)]  # el 1/11 queda fuera de la ventana
    assert almacen.ruta_local("precios", date(2026, 11, 16)).read_bytes() == original


def test_bajar_no_repite_lo_que_ya_esta_en_data(gh_falso, guardar_dias):
    guardar_dias(date(2026, 11, 17))
    almacen.subir()
    llamadas = len(gh_falso.llamadas)

    assert almacen.bajar(dias=10, hoy=date(2026, 11, 18)) == 0
    assert not any(a[1] == "download" for a in gh_falso.llamadas[llamadas:])


def test_bajar_cruza_el_cambio_de_mes(gh_falso, guardar_dias, monkeypatch, tmp_path):
    guardar_dias(date(2026, 11, 25), date(2026, 12, 1))
    almacen.subir()

    monkeypatch.setattr(ingesta, "DIR_DATOS", tmp_path / "runner" / "data")
    assert almacen.bajar(dias=10, hoy=date(2026, 12, 3)) == 2
    assert almacen.fechas_locales() == [date(2026, 11, 25), date(2026, 12, 1)]


def test_bajar_ignora_los_dias_incompletos(gh_falso, guardar_dias, monkeypatch, tmp_path):
    guardar_dias(date(2026, 11, 17), date(2026, 11, 18))
    almacen.subir()
    del gh_falso.releases["datos-2026-11"]["precios_2026-11-18.parquet"]

    monkeypatch.setattr(ingesta, "DIR_DATOS", tmp_path / "runner" / "data")
    assert almacen.bajar(dias=10, hoy=date(2026, 11, 18)) == 1
    assert almacen.fechas_locales() == [date(2026, 11, 17)]


def test_bajar_sin_releases_no_falla(gh_falso, datos_temporales):
    assert almacen.bajar(dias=10, hoy=date(2026, 11, 18)) == 0


def test_fechas_locales_ignora_carpetas_incompletas(guardar_dias, datos_temporales):
    guardar_dias(date(2026, 11, 17))
    (datos_temporales / "precios" / "fecha=2026-11-18.tmp").mkdir()
    (datos_temporales / "precios" / "fecha=2026-11-19").mkdir()  # sin archivos
    assert almacen.fechas_locales() == [date(2026, 11, 17)]


def test_sin_la_cli_de_github_sale_con_codigo_1(monkeypatch):
    def no_instalada(*args):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(almacen, "gh", no_instalada)
    assert almacen.main(["bajar"]) == 1
