"""Armado de paquetes SEPA chicos para los tests.

Genera CSV con el mismo formato que la fuente (separador `|`, CRLF, encabezado y línea de pie),
para que los tests corran el pipeline real sobre unas pocas filas.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

COLUMNAS_COMERCIO = [
    "id_comercio", "id_bandera", "comercio_cuit", "comercio_razon_social", "comercio_bandera_nombre",
    "comercio_bandera_url", "comercio_ultima_actualizacion", "comercio_version_sepa",
]
COLUMNAS_SUCURSALES = [
    "id_comercio", "id_bandera", "id_sucursal", "sucursales_nombre", "sucursales_tipo", "sucursales_calle",
    "sucursales_numero", "sucursales_latitud", "sucursales_longitud", "sucursales_observaciones",
    "sucursales_barrio", "sucursales_codigo_postal", "sucursales_localidad", "sucursales_provincia",
    "sucursales_lunes_horario_atencion", "sucursales_martes_horario_atencion",
    "sucursales_miercoles_horario_atencion", "sucursales_jueves_horario_atencion",
    "sucursales_viernes_horario_atencion", "sucursales_sabado_horario_atencion",
    "sucursales_domingo_horario_atencion",
]
COLUMNAS_PRODUCTOS = [
    "id_comercio", "id_bandera", "id_sucursal", "id_producto", "productos_ean", "productos_descripcion",
    "productos_cantidad_presentacion", "productos_unidad_medida_presentacion", "productos_marca",
    "productos_precio_lista", "productos_precio_referencia", "productos_cantidad_referencia",
    "productos_unidad_medida_referencia", "productos_precio_unitario_promo1", "productos_leyenda_promo1",
    "productos_precio_unitario_promo2", "productos_leyenda_promo2",
]

PIE = "Ultima actualizacion: 2026-11-16T01:11:59-03:00"


def ean(n: int) -> str:
    """Código de producto de 13 dígitos."""
    return f"{n:013d}"


def producto(sucursal: str, n: int, precio, bandera: int = 1) -> dict:
    """Una fila de precios. `precio` puede ser un número, un texto o None (vacío)."""
    return {"id_sucursal": sucursal, "id_producto": ean(n), "precio": precio, "id_bandera": bandera}


def productos_en(sucursal: str, cantidad: int, precio=100, desde: int = 1) -> list[dict]:
    """`cantidad` productos distintos, todos al mismo precio, en una sucursal."""
    return [producto(sucursal, desde + i, precio) for i in range(cantidad)]


def comercio(id_comercio: int = 1, sucursales: list[dict] | None = None, productos: list[dict] | None = None,
             banderas: tuple = ((1, "Bandera Uno"),), sin_columnas_productos: tuple = ()) -> dict:
    """Define un comercio. Por defecto tiene una sucursal en CABA."""
    return {
        "id_comercio": id_comercio,
        "sucursales": sucursales if sucursales is not None else [{"id_sucursal": "1"}],
        "productos": productos or [],
        "banderas": banderas,
        "sin_columnas_productos": sin_columnas_productos,
    }


def _csv(columnas: list[str], filas: list[dict]) -> str:
    def texto(valor):
        return "" if valor is None else str(valor)

    lineas = ["|".join(columnas)]
    lineas += ["|".join(texto(fila.get(c)) for c in columnas) for fila in filas]
    return "\r\n".join(lineas) + "\r\n\r\n" + PIE + "\r\n"


def contenido_comercio(id_comercio: int, sucursales: list[dict], productos: list[dict], banderas: tuple,
                       sin_columnas_productos: tuple = ()) -> dict[str, str]:
    """Texto de los tres CSV de un comercio."""
    filas_comercio = [
        {"id_comercio": id_comercio, "id_bandera": b, "comercio_cuit": "30111111111",
         "comercio_razon_social": "Razon Social", "comercio_bandera_nombre": nombre,
         "comercio_bandera_url": "http://ejemplo.com.ar", "comercio_ultima_actualizacion": "2026-11-16T01:00:00-03:00",
         "comercio_version_sepa": "1.0"}
        for b, nombre in banderas
    ]
    filas_sucursales = [
        {"id_comercio": id_comercio, "id_bandera": s.get("id_bandera", 1), "id_sucursal": s["id_sucursal"],
         "sucursales_nombre": "Sucursal " + s["id_sucursal"], "sucursales_tipo": "Supermercado",
         "sucursales_latitud": s.get("lat", -34.6037), "sucursales_longitud": s.get("lon", -58.3816),
         "sucursales_provincia": s.get("provincia", "AR-C")}
        for s in sucursales
    ]
    filas_productos = [
        {"id_comercio": id_comercio, "id_bandera": p.get("id_bandera", 1), "id_sucursal": p["id_sucursal"],
         "id_producto": p["id_producto"], "productos_ean": p.get("ean", 1),
         "productos_descripcion": "PRODUCTO " + p["id_producto"], "productos_precio_lista": p["precio"]}
        for p in productos
    ]
    columnas_productos = [c for c in COLUMNAS_PRODUCTOS if c not in sin_columnas_productos]
    return {
        "comercio.csv": _csv(COLUMNAS_COMERCIO, filas_comercio),
        "sucursales.csv": _csv(COLUMNAS_SUCURSALES, filas_sucursales),
        "productos.csv": _csv(columnas_productos, filas_productos),
    }


def escribir_carpetas(destino: Path, comercios: list[dict]) -> list[Path]:
    """Escribe los CSV de cada comercio en su carpeta (como queda después de descomprimir)."""
    carpetas = []
    for c in comercios:
        carpeta = destino / f"comercio-{c['id_comercio']}"
        carpeta.mkdir(parents=True)
        for nombre, texto in contenido_comercio(**c).items():
            (carpeta / nombre).write_bytes(texto.encode("utf-8"))  # bytes, para no alterar el CRLF
        carpetas.append(carpeta)
    return carpetas


def armar_zip(ruta: Path, fecha: date, comercios: list[dict]) -> Path:
    """Arma un paquete completo: un zip con una carpeta de fecha y un zip por comercio adentro."""
    with zipfile.ZipFile(ruta, "w") as externo:
        for c in comercios:
            interno = io.BytesIO()
            with zipfile.ZipFile(interno, "w") as zi:
                for nombre, texto in contenido_comercio(**c).items():
                    info = zipfile.ZipInfo(nombre, date_time=(fecha.year, fecha.month, fecha.day, 6, 0, 0))
                    zi.writestr(info, texto.encode("utf-8"))
            nombre_zip = f"{fecha.isoformat()}/sepa_1_comercio-sepa-{c['id_comercio']}_{fecha.isoformat()}_09-05-10.zip"
            externo.writestr(nombre_zip, interno.getvalue())
    return ruta
