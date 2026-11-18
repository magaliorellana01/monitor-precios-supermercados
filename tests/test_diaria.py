"""Tests de la ejecución diaria: el orden de los pasos y qué pasa cuando algo falla."""

from __future__ import annotations

import pytest

from src import almacen, diaria, ingesta


@pytest.fixture
def pasos(monkeypatch, datos_temporales):
    """Reemplaza los tres pasos por funciones que anotan que se llamaron."""
    anotados: list[str] = []
    monkeypatch.setattr(almacen, "bajar", lambda dias: anotados.append("bajar"))
    monkeypatch.setattr(ingesta, "main", lambda argv: anotados.append("ingesta") or 0)
    monkeypatch.setattr(almacen, "subir", lambda *a, **k: anotados.append("subir"))
    return anotados


def test_corre_los_tres_pasos_en_orden(pasos, datos_temporales):
    assert diaria.main() == 0
    assert pasos == ["bajar", "ingesta", "subir"]
    assert (datos_temporales / "ingesta" / "ultima_ejecucion.log").exists()


def test_si_la_ingesta_falla_igual_sube_y_sale_con_1(pasos, monkeypatch):
    monkeypatch.setattr(ingesta, "main", lambda argv: pasos.append("ingesta") or 1)
    assert diaria.main() == 1
    assert pasos == ["bajar", "ingesta", "subir"]


def test_si_no_se_puede_bajar_se_sigue(pasos, monkeypatch):
    def falla(dias):
        raise almacen.ErrorGh(("release", "view"), 1, "sin conexión")

    monkeypatch.setattr(almacen, "bajar", falla)
    assert diaria.main() == 0
    assert pasos == ["ingesta", "subir"]


def test_si_no_se_puede_subir_sale_con_1(pasos, monkeypatch):
    def falla(*args, **kwargs):
        raise almacen.ErrorGh(("release", "upload"), 1, "no autenticado")

    monkeypatch.setattr(almacen, "subir", falla)
    assert diaria.main() == 1
    assert pasos == ["bajar", "ingesta"]


def test_el_log_de_la_ultima_ejecucion_se_reemplaza(pasos, datos_temporales):
    diaria.main()
    diaria.main()
    texto = (datos_temporales / "ingesta" / "ultima_ejecucion.log").read_text(encoding="utf-8")
    assert texto.count("Ejecución diaria terminada") == 1
