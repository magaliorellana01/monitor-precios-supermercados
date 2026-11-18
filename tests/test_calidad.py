"""Tests de la limpieza de precios y de los controles de calidad, con datos de ejemplo chicos."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from src import calidad, ingesta
from src.calidad import ADVERTENCIA, ERROR, OK
from tests.ayudas import comercio, ean, escribir_carpetas, producto, productos_en
from tests.conftest import FECHA


# --------------------------------------------------------------------------- limpieza de precios

def test_limpieza_marca_cada_motivo_de_descarte(cargar):
    productos = [
        producto("1", 1, 100),        # bien
        producto("1", 2, 0),          # cero
        producto("1", 3, -5),         # negativo
        producto("1", 4, None),       # vacío
        producto("1", 5, 200),        # duplicado: se queda el de menor precio
        producto("1", 5, 150),
        producto("1", 6, 100),        # absurdo: 100.000 contra una mediana de 100
        producto("2", 6, 100),
        producto("3", 6, 100000),
    ]
    sucursales = [{"id_sucursal": "1"}, {"id_sucursal": "2"}, {"id_sucursal": "3"}]
    con = cargar([comercio(sucursales=sucursales, productos=productos)])

    motivos = dict(con.execute(
        "select coalesce(motivo_descarte, 'ok'), count(*) from precios_marcados_dia group by 1").fetchall())
    assert motivos == {"ok": 4, "precio_cero_o_negativo": 2, "precio_vacio": 1, "duplicado": 1, "precio_absurdo": 1}

    guardados = con.execute("select id_producto, precio_lista from precios_dia order by 1, 2").fetchall()
    assert [(p, float(precio)) for p, precio in guardados] == [
        (ean(1), 100.0), (ean(5), 150.0), (ean(6), 100.0), (ean(6), 100.0)]


def test_duplicado_con_precio_cero_se_queda_con_el_valido(cargar):
    productos = [producto("1", 1, 0), producto("1", 1, 80)]
    con = cargar([comercio(productos=productos)])
    assert [float(p) for (p,) in con.execute("select precio_lista from precios_dia").fetchall()] == [80.0]


def test_codigos_internos_se_comparan_solo_dentro_del_comercio(cargar):
    """Un código interno (ean = 0) puede repetirse en otro comercio con otro producto y otro precio."""
    barato = comercio(1, productos=[{**producto("1", 1, 10), "ean": 0}])
    caro = comercio(2, productos=[{**producto("1", 1, 100000), "ean": 0}])
    con = cargar([barato, caro])
    assert con.execute("select count(*) from precios_dia").fetchall()[0][0] == 2


def test_filtro_de_zona(cargar):
    sucursales = [
        {"id_sucursal": "caba", "provincia": "AR-C"},
        {"id_sucursal": "caba_coordenada_mala", "provincia": "AR-C", "lat": 0, "lon": 0},
        {"id_sucursal": "gba", "provincia": "AR-B", "lat": -34.70, "lon": -58.50},
        {"id_sucursal": "lejos", "provincia": "AR-B", "lat": -34.92, "lon": -57.95},  # La Plata, ~55 km
        {"id_sucursal": "cordoba", "provincia": "AR-X", "lat": -31.42, "lon": -64.18},
    ]
    productos = [producto(s["id_sucursal"], 1, 100) for s in sucursales]
    con = cargar([comercio(sucursales=sucursales, productos=productos)])
    zonas = dict(con.execute("select id_sucursal, zona from sucursales_dia").fetchall())
    assert zonas == {"caba": "CABA", "caba_coordenada_mala": "CABA", "gba": "GBA"}


# --------------------------------------------------------------------------- controles sobre los datos

def test_datos_sanos_no_dan_avisos(cargar, controlar):
    con = cargar([comercio(productos=productos_en("1", 100))])
    resultados = controlar(con)
    assert {nombre: r.resultado for nombre, r in resultados.items() if r.resultado != OK} == {}
    assert "sin día anterior" in resultados["variacion_filas"].detalle


def test_sin_precios_es_error(cargar, controlar):
    con = cargar([comercio(productos=productos_en("1", 5, precio=0))])
    assert controlar(con)["sin_precios"].resultado == ERROR


@pytest.mark.parametrize("cantidad, en_cero, esperado", [
    (200, 0, OK),
    (200, 1, ADVERTENCIA),   # 0,5%
    (100, 5, ERROR),         # 5%
])
def test_precios_invalidos(cargar, controlar, cantidad, en_cero, esperado):
    productos = productos_en("1", cantidad - en_cero) + productos_en("1", en_cero, precio=0, desde=1000)
    con = cargar([comercio(productos=productos)])
    assert controlar(con)["precios_invalidos"].resultado == esperado


def test_duplicados_dan_advertencia(cargar, controlar):
    productos = productos_en("1", 200) + [producto("1", 1, 100)]
    con = cargar([comercio(productos=productos)])
    resultado = controlar(con)["duplicados"]
    assert resultado.resultado == ADVERTENCIA
    assert "comercios: 1" in resultado.detalle


def test_precio_absurdo_da_advertencia_y_dice_cual(cargar, controlar):
    normales = [p for s in "123" for p in productos_en(s, 40)]
    absurdo = [producto("1", 900, 100), producto("2", 900, 100), producto("3", 900, 50000)]
    sucursales = [{"id_sucursal": s} for s in "123"]
    con = cargar([comercio(sucursales=sucursales, productos=normales + absurdo)])
    resultado = controlar(con)["precios_absurdos"]
    assert resultado.resultado == ADVERTENCIA
    assert ean(900) in resultado.detalle and "50000" in resultado.detalle


def test_precios_de_sucursales_que_no_estan_en_la_tabla(cargar, controlar):
    productos = productos_en("1", 100) + [producto("9", 1, 100)]  # la sucursal 9 no existe en sucursales.csv
    con = cargar([comercio(productos=productos)])
    resultado = controlar(con)["precios_sin_sucursal"]
    assert resultado.resultado == ADVERTENCIA
    assert resultado.detalle.startswith("1 de 101")


@pytest.mark.parametrize("sucursales_total, sin_precios, esperado", [
    (10, 1, ADVERTENCIA),   # 10%
    (2, 1, ERROR),          # 50%
    (10, 0, OK),
])
def test_sucursales_sin_precios(cargar, controlar, sucursales_total, sin_precios, esperado):
    ids = [str(i) for i in range(1, sucursales_total + 1)]
    con_precios = ids[: sucursales_total - sin_precios]
    productos = [p for s in con_precios for p in productos_en(s, 3)]
    con = cargar([comercio(sucursales=[{"id_sucursal": s} for s in ids], productos=productos)])
    assert controlar(con)["sucursales_sin_precios"].resultado == esperado


def test_bandera_con_precios_que_no_esta_en_comercio(cargar, controlar):
    c = comercio(sucursales=[{"id_sucursal": "1", "id_bandera": 2}],
                 productos=[producto("1", 1, 100, bandera=2)], banderas=((1, "Solo la uno"),))
    resultado = controlar(cargar([c]))["banderas_sin_comercio"]
    assert resultado.resultado == ADVERTENCIA
    assert "1-2" in resultado.detalle


# --------------------------------------------------------------------------- comparación con el día anterior

def _anterior(con, sql: str):
    """Arma las tablas del día anterior a partir de las de hoy."""
    con.execute(f"create or replace table precios_anteriores as {sql}")
    con.execute("create or replace table comercios_anteriores as select * from comercios_dia")


@pytest.mark.parametrize("sql_anterior, esperado, caida", [
    ("select * from precios_dia", OK, 0),
    ("select * from precios_dia limit 50", OK, -100),  # hoy hay más filas que ayer
    ("select * from precios_dia union all select * replace ('x' as id_sucursal) "
     "from (select * from precios_dia limit 25)", ADVERTENCIA, 20),
    ("select * from precios_dia union all select * replace ('x' as id_sucursal) "
     "from (select * from precios_dia limit 100)", ERROR, 50),
])
def test_variacion_de_filas(cargar, controlar, sql_anterior, esperado, caida):
    con = cargar([comercio(productos=productos_en("1", 100))])
    calidad.cargar_dia_anterior(con, FECHA, None)  # crea las tablas; después se pisan
    _anterior(con, sql_anterior)
    resultado = controlar(con, con_anterior=True)["variacion_filas"]
    assert resultado.resultado == esperado
    assert resultado.valor == pytest.approx(caida, abs=0.5)


def test_bandera_que_dejo_de_informar(cargar, controlar):
    con = cargar([comercio(productos=productos_en("1", 100))])
    calidad.cargar_dia_anterior(con, FECHA, None)
    _anterior(con, "select * from precios_dia union all select * replace (99 as id_comercio) "
                   "from (select * from precios_dia limit 5)")
    resultado = controlar(con, con_anterior=True)["banderas_ausentes"]
    assert resultado.resultado == ADVERTENCIA
    assert "99-1" in resultado.detalle


def test_bandera_que_informa_menos_de_la_mitad_de_sus_sucursales(cargar, controlar):
    con = cargar([comercio(productos=productos_en("1", 100))])
    calidad.cargar_dia_anterior(con, FECHA, None)
    _anterior(con, " union all ".join(
        ["select * from precios_dia"]
        + [f"select * replace ('{s}' as id_sucursal) from (select * from precios_dia limit 5)" for s in "abc"]))
    resultado = controlar(con, con_anterior=True)["caida_sucursales_bandera"]
    assert resultado.resultado == ADVERTENCIA
    assert "1-1 (4 -> 1)" in resultado.detalle


# --------------------------------------------------------------------------- columnas y fechas

def test_columna_faltante_es_error(tmp_path):
    c = comercio(productos=productos_en("1", 3), sin_columnas_productos=("productos_precio_lista",))
    carpetas = escribir_carpetas(tmp_path / "crudo", [c])
    con = duckdb.connect()
    ingesta.crear_vistas_crudas(con, carpetas)
    resultado = calidad.controlar_columnas(con, FECHA)
    assert resultado.resultado == ERROR
    assert "productos.productos_precio_lista" in resultado.detalle


def test_columnas_completas_son_ok(tmp_path):
    carpetas = escribir_carpetas(tmp_path / "crudo", [comercio(productos=productos_en("1", 3))])
    con = duckdb.connect()
    ingesta.crear_vistas_crudas(con, carpetas)
    assert calidad.controlar_columnas(con, FECHA).resultado == OK


def test_fecha_del_paquete():
    assert calidad.controlar_fecha(FECHA, "lunes", "lunes", FECHA).resultado == OK
    # el portal dice que es del 16 pero el zip trae datos de la semana anterior
    viejo = calidad.controlar_fecha(date(2026, 11, 9), "lunes", "lunes", FECHA)
    assert viejo.resultado == ERROR and "2026-11-09" in viejo.detalle
    # el archivo es de un martes y la fecha cae un lunes
    assert calidad.controlar_fecha(FECHA, "martes", "lunes", None).resultado == ERROR


def test_comercios_descartados():
    assert calidad.controlar_comercios(FECHA, []).resultado == OK
    r = calidad.controlar_comercios(FECHA, ["36: zip vacío", "47: datos viejos"])
    assert r.resultado == ADVERTENCIA and r.valor == 2


@pytest.mark.parametrize("anterior, esperado, faltan, detalle", [
    (None, OK, 0, "no hay un día anterior"),
    (date(2026, 11, 15), OK, 0, "-"),                                    # el día anterior es el 15
    (date(2026, 11, 14), ADVERTENCIA, 1, "no hay datos guardados 2026-11-15"),
    (date(2026, 11, 10), ADVERTENCIA, 5, "del 2026-11-11 al 2026-11-15"),
])
def test_continuidad_de_los_dias_guardados(anterior, esperado, faltan, detalle):
    r = calidad.controlar_continuidad(FECHA, anterior)
    assert r.resultado == esperado and r.valor == faltan and detalle in r.detalle


@pytest.mark.parametrize("ultimo, esperado", [
    (date(2026, 11, 18), OK),         # publicó hoy
    (date(2026, 11, 17), OK),         # publicó ayer (todavía no son las 13:20)
    (date(2026, 11, 16), ERROR),      # hace 2 días: el portal no se actualizó
])
def test_portal_actualizado(ultimo, esperado):
    assert calidad.controlar_portal(date(2026, 11, 18), ultimo).resultado == esperado


# --------------------------------------------------------------------------- log y día anterior

def test_el_log_no_duplica_filas_si_se_corre_dos_veces(tmp_path):
    ruta = tmp_path / "log.csv"
    calidad.registrar([calidad.ResultadoControl(FECHA, "duplicados", OK, 0, "-")], ruta)
    calidad.registrar([calidad.ResultadoControl(FECHA, "duplicados", ADVERTENCIA, 3, "comercios: 1"),
                       calidad.ResultadoControl(FECHA, "sin_precios", OK, 0, "-")], ruta)
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert lineas[0] == "fecha,control,resultado,valor,detalle"
    assert len(lineas) == 3
    assert any("duplicados,advertencia" in linea for linea in lineas)


def test_cargar_dia_anterior_usa_el_ultimo_dia_guardado_antes_de_la_fecha(cargar, datos_temporales):
    con = cargar([comercio(productos=productos_en("1", 10))])
    ingesta.guardar(con, date(2026, 11, 10))
    ingesta.guardar(con, date(2026, 11, 12))
    ingesta.guardar(con, date(2026, 11, 20))                       # posterior: no se usa
    (datos_temporales / "precios" / "fecha=2026-11-15.tmp").mkdir()  # corrida interrumpida: se ignora

    anterior = calidad.cargar_dia_anterior(con, FECHA, datos_temporales)
    assert anterior == date(2026, 11, 12)
    assert con.execute("select count(*) from precios_anteriores").fetchall()[0][0] == 10


def test_cargar_dia_anterior_sin_historial_crea_tablas_vacias(cargar, tmp_path):
    con = cargar([comercio(productos=productos_en("1", 10))])
    assert calidad.cargar_dia_anterior(con, FECHA, tmp_path / "nada") is None
    assert con.execute("select count(*) from precios_anteriores").fetchall()[0][0] == 0
