"""Tests de punta a punta: un paquete SEPA chico entra por la ingesta y los controles deciden si se guarda."""

from __future__ import annotations

import csv

import pytest

from src import calidad, ingesta
from tests.ayudas import armar_zip, comercio, productos_en
from tests.conftest import FECHA


def _cantidad_de_filas(archivo) -> int:
    return len(list(csv.DictReader(open(archivo, encoding="utf-8", newline=""))))


def test_paquete_sano_se_guarda_y_es_idempotente(tmp_path, datos_temporales):
    zip_sepa = armar_zip(tmp_path / "sepa.zip", FECHA, [comercio(productos=productos_en("1", 100))])

    assert ingesta.main(["--archivo", str(zip_sepa)]) == 0
    particion = datos_temporales / "precios" / f"fecha={FECHA.isoformat()}" / "precios.parquet"
    assert particion.exists()

    # segunda corrida: se saltea y no duplica nada
    assert ingesta.main(["--archivo", str(zip_sepa)]) == 0
    assert _cantidad_de_filas(datos_temporales / "ingesta" / "log_ingesta.csv") == 1
    # y con --forzar se reemplaza (una sola fila en el log, no dos)
    assert ingesta.main(["--archivo", str(zip_sepa), "--forzar"]) == 0
    assert _cantidad_de_filas(datos_temporales / "ingesta" / "log_ingesta.csv") == 1

    log_calidad = datos_temporales / "calidad" / "log_calidad.csv"
    resultados = {f["control"]: f["resultado"] for f in csv.DictReader(open(log_calidad, encoding="utf-8"))}
    assert set(resultados.values()) == {"ok"}
    assert len(resultados) == 13  # columnas, fecha, comercios descartados y los 10 controles de datos


def test_error_grave_no_guarda_el_dia_y_sale_con_codigo_1(tmp_path, datos_temporales):
    # la mitad de los precios en cero: supera el 1% de precios inválidos
    productos = productos_en("1", 50) + productos_en("1", 50, precio=0, desde=500)
    zip_sepa = armar_zip(tmp_path / "sepa.zip", FECHA, [comercio(productos=productos)])

    assert ingesta.main(["--archivo", str(zip_sepa)]) == 1

    assert not (datos_temporales / "precios").exists()
    assert not (datos_temporales / "ingesta" / "log_ingesta.csv").exists()
    # pero el error queda registrado
    filas = list(csv.DictReader(open(datos_temporales / "calidad" / "log_calidad.csv", encoding="utf-8")))
    errores = [f["control"] for f in filas if f["resultado"] == "error"]
    assert errores == ["precios_invalidos"]


def test_aceptar_errores_guarda_igual(tmp_path, datos_temporales):
    productos = productos_en("1", 50) + productos_en("1", 50, precio=0, desde=500)
    zip_sepa = armar_zip(tmp_path / "sepa.zip", FECHA, [comercio(productos=productos)])

    assert ingesta.main(["--archivo", str(zip_sepa), "--aceptar-errores"]) == 0
    assert (datos_temporales / "precios" / f"fecha={FECHA.isoformat()}" / "precios.parquet").exists()


def test_fecha_distinta_a_la_que_informa_el_portal_es_error(tmp_path, datos_temporales):
    zip_sepa = armar_zip(tmp_path / "sepa.zip", FECHA, [comercio(productos=productos_en("1", 100))])
    with pytest.raises(calidad.ErrorCalidad) as e:
        ingesta.procesar_zip(zip_sepa, "lunes", fecha_esperada=FECHA.replace(day=23))
    assert e.value.errores[0].control == "fecha_paquete"
    assert not (datos_temporales / "precios").exists()


def test_columna_faltante_frena_aunque_se_acepten_errores(tmp_path, datos_temporales):
    c = comercio(productos=productos_en("1", 100), sin_columnas_productos=("productos_precio_lista",))
    zip_sepa = armar_zip(tmp_path / "sepa.zip", FECHA, [c])
    assert ingesta.main(["--archivo", str(zip_sepa), "--aceptar-errores"]) == 1
    assert not (datos_temporales / "precios").exists()


def test_comercio_con_zip_vacio_se_descarta_y_el_resto_se_guarda(tmp_path, datos_temporales):
    import zipfile

    zip_sepa = armar_zip(tmp_path / "sepa.zip", FECHA, [comercio(productos=productos_en("1", 100))])
    with zipfile.ZipFile(zip_sepa, "a") as z:  # un comercio cuyo zip viene vacío, como el 36 en la fuente
        z.writestr(f"{FECHA.isoformat()}/sepa_2_comercio-sepa-36_{FECHA.isoformat()}_01-05-08.zip", b"")

    assert ingesta.main(["--archivo", str(zip_sepa)]) == 0
    filas = list(csv.DictReader(open(datos_temporales / "calidad" / "log_calidad.csv", encoding="utf-8")))
    descartados = next(f for f in filas if f["control"] == "comercios_descartados")
    assert descartados["resultado"] == "advertencia" and "comercio-sepa-36" in descartados["detalle"]


def test_dia_con_caida_fuerte_de_filas_frena(tmp_path, datos_temporales):
    ayer = armar_zip(tmp_path / "ayer.zip", FECHA.replace(day=15), [comercio(productos=productos_en("1", 200))])
    hoy = armar_zip(tmp_path / "hoy.zip", FECHA, [comercio(productos=productos_en("1", 100))])  # -50%

    assert ingesta.main(["--archivo", str(ayer)]) == 0
    assert ingesta.main(["--archivo", str(hoy)]) == 1
    assert not (datos_temporales / "precios" / f"fecha={FECHA.isoformat()}").exists()
