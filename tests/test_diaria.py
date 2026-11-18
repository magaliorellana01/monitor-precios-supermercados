"""Tests de la ejecución diaria: el orden de los pasos y qué pasa cuando algo falla."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import almacen, diaria, exportar, ingesta, ipc, modelo, reporte


@pytest.fixture
def pasos(monkeypatch, datos_temporales):
    """Reemplaza todos los pasos por funciones que anotan que se llamaron."""
    anotados: list[str] = []
    monkeypatch.setattr(almacen, "bajar", lambda dias: anotados.append("bajar"))
    monkeypatch.setattr(ingesta, "main", lambda argv: anotados.append("ingesta") or 0)
    monkeypatch.setattr(almacen, "subir", lambda *a, **k: anotados.append("subir"))
    monkeypatch.setattr(modelo, "ejecutar", lambda *a, **k: anotados.append("modelo") or 0)
    monkeypatch.setattr(ipc, "main", lambda: anotados.append("ipc") or 0)
    monkeypatch.setattr(exportar, "exportar", lambda *a, **k: anotados.append("exportar"))
    monkeypatch.setattr(almacen, "subir_dashboard", lambda *a, **k: anotados.append("dashboard"))
    monkeypatch.setattr(almacen, "bajar_logs", lambda: None)
    monkeypatch.setattr(reporte, "generar_si_corresponde", lambda *a, **k: anotados.append("reporte") or Path("r.md"))
    monkeypatch.setattr(almacen, "subir_reporte", lambda ruta: anotados.append("subir_reporte"))
    return anotados


def test_corre_todos_los_pasos_en_orden(pasos, datos_temporales):
    assert diaria.main() == 0
    assert pasos == ["bajar", "ingesta", "subir", "modelo", "ipc", "exportar", "dashboard", "reporte", "subir_reporte"]
    assert (datos_temporales / "ingesta" / "ultima_ejecucion.log").exists()


def test_si_la_ingesta_falla_igual_sube_y_sale_con_1(pasos, monkeypatch):
    monkeypatch.setattr(ingesta, "main", lambda argv: pasos.append("ingesta") or 1)
    assert diaria.main() == 1
    assert pasos == ["bajar", "ingesta", "subir", "modelo", "ipc", "exportar", "dashboard", "reporte", "subir_reporte"]


def test_si_no_se_puede_bajar_se_sigue(pasos, monkeypatch):
    def falla(dias):
        raise almacen.ErrorGh(("release", "view"), 1, "sin conexión")

    monkeypatch.setattr(almacen, "bajar", falla)
    assert diaria.main() == 0
    assert pasos == ["ingesta", "subir", "modelo", "ipc", "exportar", "dashboard", "reporte", "subir_reporte"]


def test_si_no_se_puede_subir_sale_con_1(pasos, monkeypatch):
    def falla(*args, **kwargs):
        raise almacen.ErrorGh(("release", "upload"), 1, "no autenticado")

    monkeypatch.setattr(almacen, "subir", falla)
    assert diaria.main() == 1
    assert pasos == ["bajar", "ingesta", "modelo", "ipc", "exportar", "dashboard", "reporte", "subir_reporte"]


def test_el_log_de_la_ultima_ejecucion_se_reemplaza(pasos, datos_temporales):
    diaria.main()
    diaria.main()
    texto = (datos_temporales / "ingesta" / "ultima_ejecucion.log").read_text(encoding="utf-8")
    assert texto.count("Ejecución diaria terminada") == 1


def test_si_el_modelo_devuelve_error_sale_con_1_despues_de_subir(pasos, monkeypatch):
    monkeypatch.setattr(modelo, "ejecutar", lambda *a, **k: pasos.append("modelo") or 1)
    assert diaria.main() == 1
    assert pasos == ["bajar", "ingesta", "subir", "modelo", "ipc", "exportar", "dashboard", "reporte", "subir_reporte"]


def test_si_el_modelo_se_rompe_los_datos_ya_estan_subidos(pasos, monkeypatch, datos_temporales):
    def falla(*args, **kwargs):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(modelo, "ejecutar", falla)
    assert diaria.main() == 1
    assert pasos == ["bajar", "ingesta", "subir", "ipc", "exportar", "dashboard", "reporte", "subir_reporte"]
    texto = (datos_temporales / "ingesta" / "ultima_ejecucion.log").read_text(encoding="utf-8")
    assert "No se pudo actualizar el modelo: disco lleno" in texto


def test_si_el_ipc_no_baja_el_dashboard_se_actualiza_igual(pasos, monkeypatch):
    monkeypatch.setattr(ipc, "main", lambda: pasos.append("ipc") or 1)
    assert diaria.main() == 0
    assert pasos[-5:] == ["ipc", "exportar", "dashboard", "reporte", "subir_reporte"]


def test_si_no_se_puede_subir_el_dashboard_sale_con_1(pasos, monkeypatch, datos_temporales):
    def falla(*args, **kwargs):
        raise almacen.ErrorGh(("release", "upload"), 1, "sin conexión")

    monkeypatch.setattr(almacen, "subir_dashboard", falla)
    assert diaria.main() == 1
    assert pasos[-2:] == ["ipc", "exportar"]
    texto = (datos_temporales / "ingesta" / "ultima_ejecucion.log").read_text(encoding="utf-8")
    assert "No se pudo actualizar el dashboard o el reporte" in texto


def test_si_no_toca_reporte_no_se_sube_nada(pasos, monkeypatch):
    monkeypatch.setattr(reporte, "generar_si_corresponde", lambda *a, **k: pasos.append("reporte") or None)
    assert diaria.main() == 0
    assert pasos[-2:] == ["dashboard", "reporte"]
