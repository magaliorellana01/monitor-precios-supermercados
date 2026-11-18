"""Prueba que el dashboard abre y dibuja todas sus secciones con una base chica, sin excepciones."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from tests.test_exportar import exportado, modelo_chico  # noqa: E402, F401 (fixtures)
from tests.test_modelo import construir, guardar_dia  # noqa: E402, F401 (fixtures que usa modelo_chico)

APP = Path(__file__).resolve().parent.parent / "app" / "app.py"


@pytest.fixture
def app(modelo_chico, tmp_path, monkeypatch):  # noqa: F811
    import streamlit as st

    exportado(modelo_chico, tmp_path).close()
    monkeypatch.setenv("DASHBOARD_DB", str(tmp_path / "dashboard" / "dashboard.duckdb"))
    st.cache_resource.clear()
    st.cache_data.clear()
    return AppTest.from_file(str(APP), default_timeout=60)


def test_el_dashboard_abre_sin_errores(app):
    at = app.run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Resumen", "Canasta", "Productos", "Marcas", "Inflación", "Promociones", "Metodología"]
    assert at.metric[0].label == "Canasta más barata"


@pytest.mark.parametrize("zona", ["CABA", "GBA", "TODAS"])
def test_el_dashboard_funciona_en_cada_zona(app, zona):
    at = app.run()
    at.sidebar.radio[0].set_value(zona).run()
    assert not at.exception


def test_sin_datos_publicados_muestra_un_aviso(tmp_path, monkeypatch):
    import streamlit as st

    vacia = tmp_path / "vacia.duckdb"
    import duckdb
    duckdb.connect(str(vacia)).close()
    monkeypatch.setenv("DASHBOARD_DB", str(vacia))
    st.cache_resource.clear()
    st.cache_data.clear()
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    assert any("Todavía no hay datos" in e.value for e in at.error)
