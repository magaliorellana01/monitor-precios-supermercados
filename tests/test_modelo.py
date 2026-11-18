"""Tests del modelo en DuckDB, con dos cadenas chicas y precios que dan cuentas fáciles de verificar a mano.

Cadena A (comercio 1): sucursales S1, S2, S3 en CABA y S4 en GBA.
Cadena B (comercio 2): sucursales S1 y S2 en CABA.
Canasta: dos productos, ean(1) y ean(2).
"""

from __future__ import annotations

import os
import time
from datetime import date, timedelta

import duckdb
import pytest

from src import ingesta, modelo
from tests.ayudas import comercio, ean, producto
from tests.conftest import FECHA

DIA_2 = FECHA + timedelta(days=1)
DIA_3 = FECHA + timedelta(days=2)

PARAMETROS = {
    "min_sucursales_cadena": 2,
    "min_cadenas_dispersion": 2,
    "fecha_base_indice": FECHA.isoformat(),
    "max_dias_arrastre": 3,
    "retener_dias_fct_precios": 60,
}


# --------------------------------------------------------------------------- armado de datos y configuración

def cadena_a(factor: float = 1.0):
    """Producto 1: 100, 200, 300 en CABA y 400 en GBA. Producto 2: 50 en todas."""
    precios = {"S1": 100, "S2": 200, "S3": 300, "S4": 400}
    productos = [producto(s, 1, p * factor) for s, p in precios.items()] + [producto(s, 2, 50 * factor) for s in precios]
    sucursales = [{"id_sucursal": "S1"}, {"id_sucursal": "S2"}, {"id_sucursal": "S3"},
                  {"id_sucursal": "S4", "provincia": "AR-B", "lat": -34.70, "lon": -58.50}]
    return comercio(1, sucursales=sucursales, productos=productos, banderas=((1, "Bandera A"),))


def cadena_b(sin_producto_2: bool = False, precio_1: float = 120):
    productos = [producto(s, 1, precio_1) for s in ("S1", "S2")]
    if not sin_producto_2:
        productos += [producto(s, 2, 60) for s in ("S1", "S2")]
    return comercio(2, sucursales=[{"id_sucursal": "S1"}, {"id_sucursal": "S2"}], productos=productos,
                    banderas=((1, "Bandera B"),))


def escribir_config(carpeta, parametros=None, marcas=None, cadenas=None):
    carpeta.mkdir(parents=True, exist_ok=True)
    valores = {**PARAMETROS, **(parametros or {})}
    (carpeta / "parametros.csv").write_text(
        "nombre,valor,descripcion\n" + "".join(f"{n},{v},prueba\n" for n, v in valores.items()), encoding="utf-8")
    (carpeta / "cadenas.csv").write_text(
        cadenas or "id_comercio,id_bandera,cadena,rubro\n1,1,Cadena A,supermercado\n2,1,Cadena B,supermercado\n",
        encoding="utf-8")
    (carpeta / "canasta.csv").write_text(
        f"ean,categoria,producto\n{ean(1)},Almacén,Producto uno\n{ean(2)},Almacén,Producto dos\n", encoding="utf-8")
    (carpeta / "marcas.csv").write_text(
        marcas or "categoria,rol,ean,marca,producto\n", encoding="utf-8")
    return carpeta


@pytest.fixture
def guardar_dia(cargar, datos_temporales):
    def _guardar(fecha: date, *comercios):
        ingesta.guardar(cargar(list(comercios)), fecha)
    return _guardar


@pytest.fixture
def construir(tmp_path, datos_temporales):
    """Corre el modelo y devuelve una conexión de solo lectura para consultarlo."""
    conexiones = []

    def _construir(parametros=None, marcas=None, cadenas=None, rehacer=False):
        while conexiones:  # DuckDB no deja abrir para escribir una base que otra conexión tiene abierta
            conexiones.pop().close()
        config = escribir_config(tmp_path / "config", parametros, marcas, cadenas)
        ruta = tmp_path / "modelo.duckdb"
        assert modelo.ejecutar(datos_temporales, config, ruta, rehacer=rehacer) == 0
        con = duckdb.connect(str(ruta), read_only=True)
        conexiones.append(con)
        return con

    yield _construir
    for con in conexiones:
        con.close()


def consultar(con, sql, *args):
    return con.execute(sql, list(args)).fetchall()


# --------------------------------------------------------------------------- precio representativo

def test_precio_representativo_es_la_mediana_por_zona(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    con = construir()
    mediana = dict(consultar(con, """select zona, precio_mediana from fct_precio_representativo
                                     where cadena = 'Cadena A' and clave_producto = ?""", ean(1)))
    assert {z: float(p) for z, p in mediana.items()} == {"CABA": 200.0, "GBA": 400.0, "TODAS": 250.0}


def test_solo_los_productos_con_ean_tienen_precio_representativo(guardar_dia, construir):
    interno = comercio(2, sucursales=[{"id_sucursal": "S1"}],
                       productos=[{**producto("S1", 1, 10), "ean": 0}, producto("S1", 2, 10)],
                       banderas=((1, "Bandera B"),))
    guardar_dia(FECHA, cadena_a(), interno)
    con = construir()
    claves = {c for (c,) in consultar(con, "select distinct clave_producto from fct_precios where id_comercio = 2")}
    assert claves == {"c2-" + ean(1), ean(2)}  # el código interno lleva el comercio adelante
    assert not consultar(con, "select 1 from fct_precio_representativo where clave_producto like 'c%-%'")


# --------------------------------------------------------------------------- canasta y ranking

def test_ranking_de_la_canasta(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    con = construir()
    filas = consultar(con, """select posicion, cadena, costo_canasta, sobre_la_mas_barata_pct, ahorro_vs_mas_cara_pct
                              from m_ranking_canasta_dia where zona = 'CABA' order by posicion""")
    # A en CABA: 200 + 50 = 250. B en CABA: 120 + 60 = 180.
    assert [(p, c, float(costo)) for p, c, costo, _, _ in filas] == [(1, "Cadena B", 180.0), (2, "Cadena A", 250.0)]
    assert filas[1][3] == pytest.approx(38.89, abs=0.01)   # A es 38,9% más cara que B
    assert filas[0][4] == pytest.approx(28.0, abs=0.01)    # B ahorra 28% frente a A


def test_cadena_con_pocas_sucursales_no_se_compara(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    con = construir(parametros={"min_sucursales_cadena": 3})   # B tiene 2 sucursales en CABA
    assert consultar(con, "select cadena from m_ranking_canasta_dia where zona = 'CABA'") == [("Cadena A",)]
    assert consultar(con, "select comparable from m_cadena_dia where cadena = 'Cadena B' and zona = 'CABA'") == [(False,)]


def test_una_tienda_que_no_es_supermercado_no_se_compara(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    con = construir(cadenas="id_comercio,id_bandera,cadena,rubro\n1,1,Cadena A,supermercado\n2,1,Cadena B,farmacia\n")
    assert consultar(con, "select cadena from m_ranking_canasta_dia where zona = 'CABA'") == [("Cadena A",)]


def test_canasta_incompleta_queda_fuera_del_ranking(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    guardar_dia(DIA_2, cadena_a(), cadena_b(sin_producto_2=True))
    con = construir(parametros={"max_dias_arrastre": 0})        # sin arrastre de precios
    assert consultar(con, "select cadena from m_ranking_canasta_dia where fecha = ? and zona = 'CABA'", DIA_2) == [("Cadena A",)]
    assert consultar(con, """select n_productos, completa from m_canasta_dia
                             where fecha = ? and zona = 'CABA' and cadena = 'Cadena B'""", DIA_2) == [(1, False)]


def test_faltante_temporal_se_completa_con_el_ultimo_precio(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    guardar_dia(DIA_2, cadena_a(), cadena_b(sin_producto_2=True))   # B deja de informar el producto 2 un día
    con = construir()                                               # arrastre de hasta 3 días
    fila = consultar(con, """select completa, n_productos_arrastrados, costo_canasta from m_canasta_dia
                             where fecha = ? and zona = 'CABA' and cadena = 'Cadena B'""", DIA_2)[0]
    assert fila[0] is True and fila[1] == 1 and float(fila[2]) == 180.0   # 120 de hoy + 60 de ayer


def test_el_arrastre_tiene_un_limite_de_dias(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    guardar_dia(DIA_2, cadena_a(), cadena_b(sin_producto_2=True))
    guardar_dia(DIA_3, cadena_a(), cadena_b(sin_producto_2=True))
    con = construir(parametros={"max_dias_arrastre": 1})            # el precio de hace 2 días ya no sirve
    assert consultar(con, """select completa from m_canasta_dia
                             where fecha = ? and zona = 'CABA' and cadena = 'Cadena B'""", DIA_3) == [(False,)]
    assert consultar(con, """select completa from m_canasta_dia
                             where fecha = ? and zona = 'CABA' and cadena = 'Cadena B'""", DIA_2) == [(True,)]


# --------------------------------------------------------------------------- índice

def test_indice_vale_100_el_dia_base_y_mide_la_variacion(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    guardar_dia(DIA_2, cadena_a(factor=1.10), cadena_b())           # A sube 10%, B no cambia
    con = construir()
    indices = {(f, c): float(i) for f, c, i in consultar(
        con, "select fecha, cadena, indice from m_indice_cadena_dia where zona = 'CABA'")}
    assert indices[(FECHA, "Cadena A")] == 100.0 and indices[(FECHA, "Cadena B")] == 100.0
    assert indices[(DIA_2, "Cadena A")] == pytest.approx(110.0, abs=0.01)
    assert indices[(DIA_2, "Cadena B")] == 100.0
    general = consultar(con, "select indice from m_indice_general_dia where fecha = ? and zona = 'CABA'", DIA_2)
    assert general[0][0] == pytest.approx(105.0, abs=0.01)         # mediana de 110 y 100


def test_aviso_si_nadie_tiene_la_canasta_completa_el_dia_base(guardar_dia, construir, tmp_path):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    con = construir(parametros={"fecha_base_indice": "2020-01-01"})
    assert consultar(con, "select count(*) from m_indice_cadena_dia") == [(0,)]
    assert any("índice quedó vacío" in a for a in modelo.verificar(con))


# --------------------------------------------------------------------------- dispersión y prima de marca

def test_dispersion_de_precios_entre_cadenas(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    con = construir()
    fila = consultar(con, """select n_cadenas, precio_min, precio_max, rango_pct from m_dispersion_producto_dia
                             where zona = 'CABA' and clave_producto = ?""", ean(1))[0]
    assert fila[0] == 2 and float(fila[1]) == 120.0 and float(fila[2]) == 200.0
    assert fila[3] == pytest.approx(66.7, abs=0.1)                 # 200 es 66,7% más que 120


def test_dispersion_pide_un_minimo_de_cadenas(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    con = construir(parametros={"min_cadenas_dispersion": 3})
    assert consultar(con, "select count(*) from m_dispersion_producto_dia") == [(0,)]


def test_prima_de_marca_dentro_de_cada_cadena(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    marcas = (f"categoria,rol,ean,marca,producto\n"
              f"Par de prueba,lider,{ean(1)},Marca L,Producto uno\n"
              f"Par de prueba,alternativa,{ean(2)},Marca B,Producto dos\n")
    con = construir(marcas=marcas)
    primas = {c: (float(l), float(a), p) for c, l, a, p in consultar(
        con, "select cadena, precio_lider, precio_alternativa, prima_pct from m_prima_marca_dia where zona = 'CABA'")}
    assert primas == {"Cadena A": (200.0, 50.0, 300.0), "Cadena B": (120.0, 60.0, 100.0)}


def test_sin_los_dos_productos_del_par_no_hay_prima(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b(sin_producto_2=True))
    marcas = (f"categoria,rol,ean,marca,producto\n"
              f"Par,lider,{ean(1)},L,Producto uno\n"
              f"Par,alternativa,{ean(2)},B,Producto dos\n")
    con = construir(marcas=marcas)
    assert consultar(con, "select cadena from m_prima_marca_dia where zona = 'CABA'") == [("Cadena A",)]


# --------------------------------------------------------------------------- carga incremental

def test_segunda_corrida_no_recarga_ni_duplica(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    filas = consultar(construir(), "select count(*) from fct_precios")[0][0]
    con = construir()
    assert consultar(con, "select count(*) from fct_precios") == [(filas,)]
    assert consultar(con, "select count(*) from modelo_fechas") == [(1,)]


def test_un_dia_nuevo_se_suma_al_modelo(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    construir()
    guardar_dia(DIA_2, cadena_a(), cadena_b())
    con = construir()
    assert consultar(con, "select fecha, count(*) from fct_precios group by 1 order by 1") == [(FECHA, 12), (DIA_2, 12)]
    assert consultar(con, "select count(*) from dim_fecha") == [(2,)]


def test_un_dia_reprocesado_se_vuelve_a_cargar(guardar_dia, construir, datos_temporales):
    guardar_dia(FECHA, cadena_a(), cadena_b(precio_1=120))
    construir()
    guardar_dia(FECHA, cadena_a(), cadena_b(precio_1=150))     # la ingesta corrigió el día
    archivo = datos_temporales / "precios" / f"fecha={FECHA.isoformat()}" / "precios.parquet"
    futuro = time.time() + 60
    os.utime(archivo, (futuro, futuro))

    con = construir()
    assert consultar(con, "select count(*) from fct_precios") == [(12,)]   # no se duplicó
    assert consultar(con, """select precio_mediana from fct_precio_representativo
                             where cadena = 'Cadena B' and zona = 'CABA' and clave_producto = ?""", ean(1)) == [(150,)]


def test_rehacer_da_el_mismo_resultado(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    guardar_dia(DIA_2, cadena_a(factor=1.1), cadena_b())
    sql = "select * from m_canasta_dia order by all"
    antes = consultar(construir(), sql)
    despues = consultar(construir(rehacer=True), sql)
    assert antes == despues and len(antes) > 0


def test_el_detalle_por_sucursal_se_conserva_solo_unos_dias(guardar_dia, construir):
    for i in range(3):
        guardar_dia(FECHA + timedelta(days=i), cadena_a(), cadena_b())
    con = construir(parametros={"retener_dias_fct_precios": 1})
    assert [f for (f,) in consultar(con, "select distinct fecha from fct_precios order by 1")] == [DIA_2, DIA_3]
    # la historia agregada se conserva entera
    assert consultar(con, "select count(distinct fecha) from fct_precio_representativo") == [(3,)]


# --------------------------------------------------------------------------- dimensiones y avisos

def test_bandera_sin_clasificar_se_avisa(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    con = construir(cadenas="id_comercio,id_bandera,cadena,rubro\n1,1,Cadena A,supermercado\n")   # falta B
    assert consultar(con, "select rubro from dim_cadena where id_comercio = 2") == [("sin_clasificar",)]
    assert any("Bandera B" in a and "config/cadenas.csv" in a for a in modelo.verificar(con))


def test_unidades_y_contenido_de_los_productos(guardar_dia, construir):
    # una cadena informa "1 UNI" para todo y la otra informa el peso real: gana la que informa el peso
    a = comercio(1, productos=[{**producto("1", 1, 100), "cantidad": 1, "unidad": "UNI", "marca": "Marca X"},
                               {**producto("1", 2, 100), "cantidad": 1.5, "unidad": "kg", "marca": "Marca Y"}])
    b = comercio(2, productos=[{**producto("1", 1, 100), "cantidad": 500, "unidad": "gr.", "marca": "marca x"},
                               {**producto("1", 2, 100), "cantidad": 1.5, "unidad": "Kg", "marca": "Marca Y"}],
                 banderas=((1, "Bandera B"),))
    guardar_dia(FECHA, a, b)
    con = construir()
    filas = {c: (cont, u, m) for c, cont, u, m in consultar(
        con, "select clave_producto, contenido, unidad, marca from dim_producto")}
    assert filas[ean(1)] == (500.0, "g", "MARCA X")
    assert filas[ean(2)] == (1500.0, "g", "MARCA Y")


def test_dim_fecha_marca_los_dias_sin_datos(guardar_dia, construir):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    guardar_dia(DIA_3, cadena_a(), cadena_b())                      # falta el día del medio
    con = construir()
    assert consultar(con, "select fecha, tiene_datos, nombre_dia from dim_fecha order by fecha") == [
        (FECHA, True, "lunes"), (DIA_2, False, "martes"), (DIA_3, True, "miércoles")]


def test_sin_dias_guardados_sale_con_error(tmp_path):
    assert modelo.ejecutar(tmp_path / "vacia", tmp_path / "config", tmp_path / "m.duckdb") == 1


def test_fechas_disponibles_ignora_los_dias_incompletos(guardar_dia, datos_temporales):
    guardar_dia(FECHA, cadena_a(), cadena_b())
    (datos_temporales / "productos" / f"fecha={FECHA.isoformat()}" / "productos.parquet").unlink()
    (datos_temporales / "precios" / "fecha=2026-11-20.tmp").mkdir()
    assert modelo.fechas_disponibles(datos_temporales) == {}


def test_marcador_sin_reemplazar_es_un_error(tmp_path):
    archivo = tmp_path / "x.sql"
    archivo.write_text("select '{{FECHA}}'", encoding="utf-8")
    with pytest.raises(ValueError, match="sin reemplazar"):
        modelo.texto_sql(archivo, {"DIR_DATOS": "x"})
