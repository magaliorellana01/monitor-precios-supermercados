"""Tests de la ejecución diaria: el orden de los pasos y qué pasa cuando algo falla."""

from __future__ import annotations

import pytest

from src import almacen, diaria, ingesta, modelo


@pytest.fixture
def pasos(monkeypatch, datos_temporales):
    """Reemplaza los cuatro pasos por funciones que anotan que se llamaron."""
    anotados: list[str] = []
    monkeypatch.setattr(almacen, "bajar", lambda dias: anotados.append("bajar"))
    monkeypatch.setattr(ingesta, "main", lambda argv: anotados.append("ingesta") or 0)
    monkeypatch.setattr(almacen, "subir", lambda *a, **k: anotados.append("subir"))
    monkeypatch.setattr(modelo, "ejecutar", lambda *a, **k: anotados.append("modelo") or 0)
    return anotados


def test_corre_los_cuatro_pasos_en_orden(pasos, datos_temporales):
    assert diaria.main() == 0
    assert pasos == ["bajar", "ingesta", "subir", "modelo"]
    assert (datos_temporales / "ingesta" / "ultima_ejecucion.log").exists()


def test_si_la_ingesta_falla_igual_sube_y_sale_con_1(pasos, monkeypatch):
    monkeypatch.setattr(ingesta, "main", lambda argv: pasos.append("ingesta") or 1)
    assert diaria.main() == 1
    assert pasos == ["bajar", "ingesta", "subir", "modelo"]


def test_si_no_se_puede_bajar_se_sigue(pasos, monkeypatch):
    def falla(dias):
        raise almacen.ErrorGh(("release", "view"), 1, "sin conexión")

    monkeypatch.setattr(almacen, "bajar", falla)
    assert diaria.main() == 0
    assert pasos == ["ingesta", "subir", "modelo"]


def test_si_no_se_puede_subir_sale_con_1(pasos, monkeypatch):
    def falla(*args, **kwargs):
        raise almacen.ErrorGh(("release", "upload"), 1, "no autenticado")

    monkeypatch.setattr(almacen, "subir", falla)
    assert diaria.main() == 1
    assert pasos == ["bajar", "ingesta", "modelo"]


def test_el_log_de_la_ultima_ejecucion_se_reemplaza(pasos, datos_temporales):
    diaria.main()
    diaria.main()
    texto = (datos_temporales / "ingesta" / "ultima_ejecucion.log").read_text(encoding="utf-8")
    assert texto.count("Ejecución diaria terminada") == 1


def test_si_el_modelo_devuelve_error_sale_con_1_despues_de_subir(pasos, monkeypatch):
    monkeypatch.setattr(modelo, "ejecutar", lambda *a, **k: pasos.append("modelo") or 1)
    assert diaria.main() == 1
    assert pasos == ["bajar", "ingesta", "subir", "modelo"]


def test_si_el_modelo_se_rompe_los_datos_ya_estan_subidos(pasos, monkeypatch, datos_temporales):
    def falla(*args, **kwargs):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(modelo, "ejecutar", falla)
    assert diaria.main() == 1
    assert pasos == ["bajar", "ingesta", "subir"]
    texto = (datos_temporales / "ingesta" / "ultima_ejecucion.log").read_text(encoding="utf-8")
    assert "No se pudo actualizar el modelo: disco lleno" in texto
