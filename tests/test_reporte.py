"""Tests del reporte semanal, con una base de dashboard chica armada a mano.

Cinco cadenas (A a E) y dos productos. Hay datos todos los días de dos semanas completas: la del 9 al 15 de noviembre
y la del 16 al 22. Desde el 18, el producto 1 de la cadena E sube 10% (de 200 a 220): su costo pasa de 260 a 280 y supera a D (265), así que E baja del puesto 4 al 5.
"""

from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pytest

from src import almacen, reporte

LUNES_1 = date(2026, 11, 9)
LUNES_2 = date(2026, 11, 16)
# (precio del producto 1, precio del producto 2) por cadena. Costos: A=150, B=160, C=170, E=260, D=265.
PRECIOS = {"Cadena A": (100, 50), "Cadena B": (110, 50), "Cadena C": (120, 50), "Cadena D": (205, 60), "Cadena E": (200, 60)}


def precio(cadena: str, n: int, fecha: date) -> float:
    base = PRECIOS[cadena][n - 1]
    return base * 1.10 if (cadena == "Cadena E" and n == 1 and fecha >= date(2026, 11, 18)) else base


@pytest.fixture
def dashboard(tmp_path):
    ruta = tmp_path / "dashboard.duckdb"
    con = duckdb.connect(str(ruta))
    con.execute("create table m_canasta_dia (fecha date, cadena varchar, zona varchar, comparable boolean, completa boolean)")
    con.execute("create table m_ranking_canasta_dia (fecha date, zona varchar, cadena varchar, costo_canasta decimal(38,2), "
                "posicion integer, n_cadenas integer, sobre_la_mas_barata_pct double, ahorro_vs_mas_cara_pct double)")
    con.execute("create table m_indice_general_dia (fecha date, zona varchar, n_cadenas integer, indice double)")
    con.execute("create table precio_canasta_dia (fecha date, cadena varchar, zona varchar, clave_producto varchar, "
                "categoria varchar, producto varchar, n_sucursales integer, precio_mediana decimal(12,2))")
    con.execute("create table m_promo_cadena_dia (fecha date, cadena varchar, filas integer, filas_promo integer, "
                "pct_con_promo double, descuento_mediano_pct double)")

    fechas = [LUNES_1 + timedelta(days=i) for i in range(14)]
    base_indice = {}
    for fecha in fechas:
        costos = {c: precio(c, 1, fecha) + precio(c, 2, fecha) for c in PRECIOS}
        orden = sorted(costos, key=costos.get)
        for pos, cadena in enumerate(orden, start=1):
            costo = costos[cadena]
            con.execute("insert into m_canasta_dia values (?, ?, 'TODAS', true, true)", [fecha, cadena])
            con.execute("insert into m_ranking_canasta_dia values (?, 'TODAS', ?, ?, ?, 5, ?, ?)",
                        [fecha, cadena, costo, pos, round(100 * (costo / costos[orden[0]] - 1), 2),
                         round(100 * (1 - costo / costos[orden[-1]]), 2)])
            base_indice.setdefault(cadena, costo)
            for n in (1, 2):
                con.execute("insert into precio_canasta_dia values (?, ?, 'TODAS', ?, 'Almacén', ?, 3, ?)",
                            [fecha, cadena, f"ean{n}", f"Producto {n}", precio(cadena, n, fecha)])
        indice = sorted(costos[c] / base_indice[c] * 100 for c in costos)[2]  # mediana de 5
        con.execute("insert into m_indice_general_dia values (?, 'TODAS', 5, ?)", [fecha, indice])
        con.execute("insert into m_promo_cadena_dia values (?, 'Cadena A', 10000, 2000, 20.0, 25.0)", [fecha])
        con.execute("insert into m_promo_cadena_dia values (?, 'Cadena B', 10000, 10, 0.1, 5.0)", [fecha])
    con.close()
    return ruta


@pytest.fixture
def carpeta(tmp_path):
    return tmp_path / "reportes"


# --------------------------------------------------------------------------- fechas

def test_lunes_de_cualquier_dia_de_la_semana():
    assert reporte.lunes_de(date(2026, 11, 22)) == LUNES_2  # domingo
    assert reporte.lunes_de(LUNES_2) == LUNES_2


def test_ultima_semana_completa():
    assert reporte.ultima_semana_completa(date(2026, 11, 22)) == LUNES_2  # el domingo cierra la semana
    assert reporte.ultima_semana_completa(date(2026, 11, 18)) == LUNES_1  # a mitad de semana, la anterior
    assert reporte.ultima_semana_completa(date(2026, 11, 16)) == LUNES_1


def test_elegir_fechas_compara_con_el_cierre_de_la_semana_anterior():
    disponibles = [LUNES_1 + timedelta(days=i) for i in range(14)]
    assert reporte.elegir_fechas(disponibles, LUNES_2) == (date(2026, 11, 22), date(2026, 11, 15), True)


def test_elegir_fechas_sin_semana_anterior_compara_con_el_primer_dia():
    disponibles = [LUNES_1 + timedelta(days=i) for i in range(7)]
    assert reporte.elegir_fechas(disponibles, LUNES_1) == (date(2026, 11, 15), LUNES_1, False)


def test_elegir_fechas_sin_datos_de_la_semana_falla():
    with pytest.raises(reporte.SinSemana):
        reporte.elegir_fechas([LUNES_1], LUNES_2)


# --------------------------------------------------------------------------- contenido

def test_el_reporte_cuenta_lo_que_paso_en_la_semana(dashboard, carpeta):
    texto = reporte.generar(LUNES_2, dashboard, carpeta).read_text(encoding="utf-8")
    assert "Semana del 16 al 22 de noviembre de 2026" in texto
    assert "7 de 7 días con datos" in texto and "Semana incompleta" not in texto
    assert "**Canasta más barata:** Cadena A ($ 150)" in texto
    assert "Cadena E ($ 280)" in texto  # la más cara al cierre
    assert "Cadena E (4° → 5°)" in texto and "Cadena D (5° → 4°)" in texto  # cambios de posición
    # E subió 20 de 260: +7,7 %
    assert "| 5° | Cadena E | $ 280 |" in texto and "+7,7 %" in texto
    # solo subió el producto 1 de la cadena E: la mediana entre cadenas no se mueve y ningún producto figura como cambiado
    assert "Ninguno." in texto


def test_productos_que_mas_cambian_usan_la_mediana_entre_cadenas(dashboard, carpeta):
    # Si suben cuatro de las cinco cadenas, la mediana del producto sube y aparece en el reporte.
    con = duckdb.connect(str(dashboard))
    con.execute("update precio_canasta_dia set precio_mediana = precio_mediana * 1.2 "
                "where fecha >= date '2026-11-18' and clave_producto = 'ean2' and cadena <> 'Cadena A'")
    con.close()
    texto = reporte.generar(LUNES_2, dashboard, carpeta).read_text(encoding="utf-8")
    assert "| Producto 2 | Almacén |" in texto and "+20,0 %" in texto


def test_promociones_solo_de_cadenas_con_volumen(dashboard, carpeta):
    texto = reporte.generar(LUNES_2, dashboard, carpeta).read_text(encoding="utf-8")
    assert "| Cadena A | 20,0 % | 25,0 % | 7 |" in texto
    assert "Cadena B | 0,1" not in texto  # 10 filas por día: no alcanza


def test_semana_incompleta_se_avisa(dashboard, carpeta):
    con = duckdb.connect(str(dashboard))
    for tabla in ("m_canasta_dia", "m_ranking_canasta_dia", "m_indice_general_dia", "precio_canasta_dia", "m_promo_cadena_dia"):
        con.execute(f"delete from {tabla} where fecha > date '2026-11-18'")
    con.close()
    texto = reporte.generar(LUNES_2, dashboard, carpeta).read_text(encoding="utf-8")
    assert "3 de 7 días con datos" in texto and "Semana incompleta" in texto


def test_avisos_de_calidad_salen_del_log(dashboard, carpeta, tmp_path):
    log = tmp_path / "log_calidad.csv"
    log.write_text("fecha,control,resultado,valor,detalle\n"
                   "2026-11-17,precios_absurdos,advertencia,0.002,117 casos\n"
                   "2026-11-18,precios_absurdos,advertencia,0.002,90 casos\n"
                   "2026-11-18,duplicados,ok,0,-\n"
                   "2026-11-05,sin_precios,error,1,fuera de la semana\n", encoding="utf-8")
    texto = reporte.generar(LUNES_2, dashboard, carpeta, log).read_text(encoding="utf-8")
    assert "precios_absurdos (advertencia, 2 día(s))" in texto
    assert "sin_precios" not in texto and "duplicados" not in texto


def test_sin_log_de_calidad_lo_dice(dashboard, carpeta, tmp_path):
    texto = reporte.generar(LUNES_2, dashboard, carpeta, tmp_path / "no_hay.csv").read_text(encoding="utf-8")
    assert "no se encontró el log" in texto


# --------------------------------------------------------------------------- cuándo sale solo

def test_se_genera_una_sola_vez_por_semana(dashboard, carpeta, tmp_path):
    sin_log = tmp_path / "no_hay.csv"
    primero = reporte.generar_si_corresponde(dashboard, carpeta, sin_log)
    assert primero == carpeta / "2026-11-16.md" and primero.exists()
    assert reporte.generar_si_corresponde(dashboard, carpeta, sin_log) is None


def test_una_semana_con_pocos_dias_no_sale_sola(dashboard, carpeta):
    con = duckdb.connect(str(dashboard))
    for tabla in ("m_canasta_dia", "m_ranking_canasta_dia", "m_indice_general_dia", "precio_canasta_dia", "m_promo_cadena_dia"):
        con.execute(f"delete from {tabla} where fecha between date '2026-11-12' and date '2026-11-22'")  # quedan 3 días de la semana 1
    con.close()
    assert reporte.generar_si_corresponde(dashboard, carpeta) is None


def test_sin_dashboard_falla_con_un_mensaje_claro(carpeta, tmp_path):
    with pytest.raises(FileNotFoundError, match="src.exportar"):
        reporte.generar(LUNES_2, tmp_path / "no_existe.duckdb", carpeta)


# --------------------------------------------------------------------------- subida

def test_subir_reporte_crea_el_release_una_vez(monkeypatch, tmp_path):
    llamadas = []
    creado = []

    def gh(*args):
        llamadas.append(args)
        if args[1] == "view" and not creado:
            raise almacen.ErrorGh(args, 1, "release not found")
        if args[1] == "create":
            creado.append(True)
        return '{"assets": []}'

    monkeypatch.setattr(almacen, "gh", gh)
    archivo = tmp_path / "2026-11-16.md"
    archivo.write_text("x", encoding="utf-8")
    almacen.subir_reporte(archivo)
    almacen.subir_reporte(archivo)
    ordenes = [a[1] for a in llamadas]
    assert ordenes.count("create") == 1 and ordenes.count("upload") == 2
    assert all("--clobber" in a for a in llamadas if a[1] == "upload")
