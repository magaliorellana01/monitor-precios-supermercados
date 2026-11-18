"""Tests de la base chica del dashboard y de la métrica de promociones que la alimenta."""

from __future__ import annotations

import duckdb
import pytest

from src import almacen, exportar
from tests.ayudas import comercio, ean, producto
from tests.conftest import FECHA
from tests.test_modelo import DIA_2, cadena_a, cadena_b, consultar, construir, guardar_dia  # noqa: F401 (fixtures)


@pytest.fixture
def modelo_chico(guardar_dia, construir, tmp_path):  # noqa: F811
    guardar_dia(FECHA, cadena_a(), cadena_b())
    guardar_dia(DIA_2, cadena_a(), cadena_b())
    construir().close()
    return tmp_path / "modelo.duckdb"


def exportado(modelo_chico, tmp_path, ipc=None):
    ruta = exportar.exportar(modelo_chico, tmp_path / "dashboard" / "dashboard.duckdb", ipc or tmp_path / "no_hay.csv")
    return duckdb.connect(str(ruta), read_only=True)


def test_la_base_del_dashboard_tiene_las_tablas_que_lee_la_app(modelo_chico, tmp_path):
    con = exportado(modelo_chico, tmp_path)
    tablas = {t for (t,) in con.execute("show tables").fetchall()}
    esperadas = set(exportar.TABLAS) | set(exportar.CONSULTAS) | {"ipc", "meta"}
    assert esperadas <= tablas
    con.close()


def test_meta_resume_el_rango_de_dias(modelo_chico, tmp_path):
    con = exportado(modelo_chico, tmp_path)
    desde, hasta, dias = consultar(con, "select fecha_desde, fecha_hasta, dias from meta")[0]
    assert (desde, hasta, dias) == (FECHA, DIA_2, 2)
    con.close()


def test_solo_viajan_los_productos_de_la_canasta(modelo_chico, tmp_path):
    con = exportado(modelo_chico, tmp_path)
    claves = {c for (c,) in consultar(con, "select distinct clave_producto from precio_canasta_dia")}
    assert claves <= {ean(1), ean(2)}
    assert {c for (c,) in consultar(con, "select distinct clave_producto from m_dispersion_producto_dia")} <= claves
    con.close()


def test_sin_ipc_la_tabla_queda_vacia_y_con_ipc_se_carga(modelo_chico, tmp_path):
    con = exportado(modelo_chico, tmp_path)
    assert consultar(con, "select count(*) from ipc") == [(0,)]
    con.close()

    csv = tmp_path / "ipc.csv"
    csv.write_text("fecha,variacion_mensual_pct\n2026-09-30,1.9\n2026-10-31,2.2\n", encoding="utf-8")
    con = exportado(modelo_chico, tmp_path, csv)
    assert consultar(con, "select variacion_mensual_pct from ipc order by fecha") == [(1.9,), (2.2,)]
    con.close()


def test_sin_modelo_falla_con_un_mensaje_claro(tmp_path):
    with pytest.raises(FileNotFoundError, match="src.modelo"):
        exportar.exportar(tmp_path / "no_existe.duckdb", tmp_path / "d.duckdb")


def test_promociones_por_cadena_y_dia(guardar_dia, construir):
    # Cadena A: producto 1 con precio de lista 100 en S1..S4; en S1 y S2 hay promoción de 80 (20% menos).
    productos = [{**producto(s, 1, 100), "promo1": 80 if s in ("S1", "S2") else None} for s in ("S1", "S2", "S3", "S4")]
    base = cadena_a()
    base["productos"] = productos
    guardar_dia(FECHA, base, cadena_b())
    con = construir()
    fila = consultar(con, "select filas, filas_promo, pct_con_promo, descuento_mediano_pct from m_promo_cadena_dia "
                          "where cadena = 'Cadena A' and fecha = ?", FECHA)[0]
    assert fila == (4, 2, 50.0, 20.0)
    sin_promo = consultar(con, "select filas_promo, descuento_mediano_pct from m_promo_cadena_dia where cadena = 'Cadena B'")
    assert sin_promo == [(0, None)]


def test_subir_dashboard_reemplaza_la_base_del_release(monkeypatch, tmp_path):
    llamadas = []
    existentes = {"datos-dashboard": None}

    def gh(*args):
        llamadas.append(args)
        if args[1] == "view":
            if existentes["datos-dashboard"] is None:
                raise almacen.ErrorGh(args, 1, "release not found")
            return '{"assets": []}'
        if args[1] == "create":
            existentes["datos-dashboard"] = True
        return ""

    monkeypatch.setattr(almacen, "gh", gh)
    base = tmp_path / "dashboard.duckdb"
    base.write_bytes(b"x")
    almacen.subir_dashboard(base)
    almacen.subir_dashboard(base)
    ordenes = [a[1] for a in llamadas]
    assert ordenes.count("create") == 1  # el Release se crea una sola vez
    assert ordenes.count("upload") == 2 and all("--clobber" in a for a in llamadas if a[1] == "upload")


def test_subir_dashboard_sin_archivo_falla(tmp_path):
    with pytest.raises(FileNotFoundError, match="src.exportar"):
        almacen.subir_dashboard(tmp_path / "no_existe.duckdb")


def test_subir_dashboard_desde_la_linea_de_comandos_avisa_si_falta_gh(monkeypatch, tmp_path):
    def sin_gh(*args):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(almacen, "gh", sin_gh)
    monkeypatch.setattr(exportar, "RUTA_DASHBOARD", tmp_path / "dashboard.duckdb")
    (tmp_path / "dashboard.duckdb").write_bytes(b"x")
    assert almacen.main(["subir-dashboard"]) == 1
