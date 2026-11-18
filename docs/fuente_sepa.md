# Fuente: Precios Claros - Base SEPA

Documentación de la fuente, armada en la etapa 0 a partir del paquete del **lunes 16/11/2026**.
La exploración completa está en [`notebooks/00_reconocimiento.ipynb`](../notebooks/00_reconocimiento.ipynb).

## Qué es

El SEPA (Sistema Electrónico de Publicidad de Precios Argentinos) obliga a los comercios minoristas grandes a
informar todos los días los precios de cada producto en cada sucursal. La Secretaría de Comercio publica
esos datos como datos abiertos (licencia Creative Commons Atribución 4.0).

La especificación oficial de los archivos es el Anexo II de la disposición SEPA. Se puede bajar de los recursos del dataset ("Metadata").

## Dónde se descarga

| | |
|---|---|
| Portal de origen | `https://datos.produccion.gob.ar/dataset/sepa-precios` |
| API (CKAN) | `https://datos.produccion.gob.ar/api/3/action/package_show?id=sepa-precios` |
| Espejo | `datos.gob.ar`, dataset `precios-claros-base-sepa`. **No usarlo:** sus fechas estaban desactualizadas. |

Hay **un zip por día de la semana**, en URLs fijas:

```
https://datos.produccion.gob.ar/dataset/6f47ec76-d1ce-4e34-a7e1-621fe9b1d0b5/resource/<id_recurso>/download/sepa_<dia>.zip
```

| Día | id_recurso |
|---|---|
| lunes | `0a9069a9-06e8-4f98-874d-da5578693290` |
| martes | `9dc06241-cc83-44f4-8e25-c9b1636b8bc8` |
| miércoles | `1e92cd42-4f94-4071-a165-62c4cb2ce23c` |
| jueves | `d076720f-a7f0-4af8-b1d6-1b99d5a90c14` |
| viernes | `91bc072a-4726-44a1-85ec-4a8467aad27e` |
| sábado | `b3c3da5d-213d-41e7-8d74-f23fda0a3c30` |
| domingo | `f8e75128-515a-436e-bf8d-5c63a62f2005` |

El pipeline no debería depender de estos ids fijos. Conviene que consulte la API CKAN y tome la URL del recurso cuyo nombre es el día de la semana.

## Cuándo se actualiza

- Los comercios envían los datos hasta las **06:00** y pueden rectificarlos hasta las **10:00**.
- El portal publica el zip del día alrededor de las **13:20 hora argentina** (16:20 UTC).
- Cada zip **se pisa a la semana siguiente**, así que el portal guarda una **ventana móvil de 7 días**:
  - Si una descarga falla, hay hasta 6 días para recuperarla.
  - Al arrancar se pueden bajar los últimos 7 días de una vez.
  - **Antes de las 13:20, `sepa_<hoy>.zip` todavía tiene los datos de hace una semana.** La fecha válida es la de la carpeta interna del zip, no la del día en que se descarga.

## Estructura del paquete

```
sepa_lunes.zip                                  (~335 MB)
└── 2026-11-16/                                 ← fecha del paquete
    ├── sepa_1_comercio-sepa-12_2026-11-16_09-05-10.zip   ← un zip por comercio
    │   ├── comercio.csv
    │   ├── sucursales.csv
    │   └── productos.csv
    ├── sepa_2_comercio-sepa-10_2026-11-16_01-05-08.zip
    └── ...  (17 zips)
```

### Formato de los CSV

- Separador `|`, codificación UTF-8 (algunos archivos con BOM), fin de línea CRLF, con encabezado.
- Al final hay una línea en blanco y un pie `Ultima actualizacion: <fecha ISO>`. **No es un dato**: se descarta
  leyendo todo como texto y quedándose con las filas cuyo `id_comercio` es numérico.
- Los números usan punto decimal.

## Tablas y columnas

### `comercio.csv`: una fila por bandera

| Columna | Descripción |
|---|---|
| `id_comercio` | Id de la empresa asignado por la Secretaría. |
| `id_bandera` | Id de la bandera dentro del comercio (1, 2, 3…). Por ejemplo, Cencosud: Vea, Disco, Jumbo. |
| `comercio_cuit`, `comercio_razon_social` | Datos fiscales. |
| `comercio_bandera_nombre`, `comercio_bandera_url` | Nombre comercial y web. |
| `comercio_ultima_actualizacion` | Fecha declarada. **No es confiable** (Changomas declara 2017). |
| `comercio_version_sepa` | Versión de la especificación ("1.0"). |

### `sucursales.csv`: una fila por sucursal

| Columna | Descripción |
|---|---|
| `id_comercio`, `id_bandera`, `id_sucursal` | Clave de la sucursal. `id_sucursal` solo es único dentro del comercio. |
| `sucursales_nombre`, `sucursales_tipo` | Tipo: Hipermercado (más de 15 cajas), Supermercado (4 a 15), Autoservicio (1 a 3), Web. |
| `sucursales_calle`, `sucursales_numero`, `sucursales_barrio`, `sucursales_codigo_postal` | Dirección. |
| `sucursales_localidad` | Texto libre, **no sirve para filtrar**. |
| `sucursales_provincia` | Código ISO 3166-2 (`AR-C` CABA, `AR-B` Buenos Aires…). Hay 61 vacías. |
| `sucursales_latitud`, `sucursales_longitud` | Coordenadas WGS84. **Completas en todas las sucursales.** |
| `sucursales_<dia>_horario_atencion` | Horarios por día. |

### `productos.csv`: una fila por sucursal y producto (es la tabla de precios)

| Columna | Descripción |
|---|---|
| `id_comercio`, `id_bandera`, `id_sucursal` | Sucursal. |
| `id_producto` | Código de 13 dígitos. Es el **EAN/UPC** cuando `productos_ean = 1`. |
| `productos_ean` | 1 = EAN estándar (comparable entre cadenas); 0 = código interno del comercio. |
| `productos_descripcion`, `productos_marca` | Texto libre de cada cadena (DIA abrevia: "LA SE", "MANFR"). |
| `productos_cantidad_presentacion`, `productos_unidad_medida_presentacion` | Tamaño del envase. Las unidades no están normalizadas ("GR", "gr", "gr.", "grm"…). |
| `productos_precio_lista` | **Precio sin descuentos**, para cualquier consumidor. Es el precio principal. |
| `productos_precio_referencia`, `productos_cantidad_referencia`, `productos_unidad_medida_referencia` | Precio por kg, litro, etc. |
| `productos_precio_unitario_promo1`, `productos_leyenda_promo1` | Promoción de alcance general (3x2, % de descuento). |
| `productos_precio_unitario_promo2`, `productos_leyenda_promo2` | Promoción con condiciones (tarjetas, medios de pago, jubilados). |

## Tamaños (paquete del 16/11/2026)

| Medida | Valor |
|---|---|
| Zip externo | 335 MB (se descarga en ~10 s) |
| CSV descomprimidos | 1,68 GB |
| Filas de precios | 14,9 millones |
| Comercios / banderas | 16 / 29 |
| Sucursales | 3.016 |
| Productos distintos | 81 mil (77,7 mil con EAN) |
| Lectura completa con DuckDB | ~8 s |

Las cadenas más grandes en filas son DIA (4,3 M), Carrefour (3,4 M), Changomas (2,6 M), Cencosud (1,3 M), Coto (1,0 M) y La Anónima (1,0 M).

### Tamaño por día según el filtro (Parquet zstd, tabla de precios normalizada)

| Escenario | Filas | MB por día | GB por año |
|---|---|---|---|
| Todo el país | 14,9 M | 34,8 | 12,7 |
| Solo CABA | 4,2 M | 8,1 | 3,0 |
| **CABA + GBA (40 km del Obelisco)** | 7,5 M | 15,2 | 5,5 |
| CABA + GBA, solo EAN en 3 o más comercios | 4,5 M | 7,0 | 2,5 |
| CABA + GBA agregado por bandera, producto y zona | 0,36 M | 2,8 | 1,0 |
| Tabla de productos (descripción, marca, envase) | 81 mil | 1,8 | (se actualiza poco) |

## Identificar un producto entre cadenas

El **EAN** (`id_producto` con `productos_ean = 1`) es el identificador común: el mismo código es el mismo
producto en todas las cadenas. El 99% de las filas lo usa.

| Presente en… | Productos |
|---|---|
| 10 o más comercios | 204 |
| 7 o más comercios | 2.601 |
| 3 o más comercios | 12.027 |
| 1 solo comercio | 57.062 |

Algunos comercios no son supermercados (Farmacity, la tienda de Axion), así que el máximo real para alimentos
ronda los 10 comercios. Hay suficientes productos comunes para armar una canasta de unos 30 productos.

## Promociones

- Promo1 aparece en el 8,7% de las filas y promo2 en el 3,4%.
- Casi todas vienen de **DIA** (22,5% de sus filas con promo1) y de la **Cooperativa Obrera** (16,6%).
  Carrefour 4,9%, La Anónima 2,1%, Coto 0,8%. **La mitad de los comercios no informa ninguna promoción.**
- Las leyendas son texto libre y no siempre traen la vigencia.
- Por lo tanto, el análisis de promociones solo es viable para DIA y la Cooperativa Obrera.

## Problemas de calidad encontrados

| Problema | Magnitud (16/11) | Qué hacer |
|---|---|---|
| Zip de un comercio vacío (0 bytes) | comercio 36 | Registrar como advertencia y seguir con el resto. |
| Comercio que republica datos viejos | comercio 47 (Unicoop): CSV del 11/06/2025 | Descartar si la fecha del CSV tiene más de 2 días de diferencia con la del paquete. |
| `comercio_ultima_actualizacion` incorrecta | Changomas: 2017 y 2021 | No usar. La fecha válida es la de la carpeta del zip. |
| Comercios que publican la tarde anterior | 4 comercios (fecha del CSV = día anterior) | Es normal, aceptarlo. |
| Precio vacío | 29 filas | Descartar. |
| Precio en cero | 70 filas | Descartar. |
| Precios de más de 5 millones | 332 filas, casi todas electrónica | No usar un tope fijo: comparar contra la mediana del producto. |
| Duplicados (sucursal + producto) | 49 | Quedarse con una fila. |
| Precios de sucursales que no están en `sucursales.csv` | 55 mil filas de 14 sucursales | Advertencia. Quedan fuera del filtro por zona porque no tienen coordenadas. |
| Sucursales sin precios | 30 | Ignorar. |
| Coordenadas mal cargadas | 33 sucursales de CABA a más de 20 km del Obelisco, 1 fuera del país | Si la provincia es `AR-C`, va en CABA aunque la coordenada esté mal. |
| Provincia vacía o en texto | 61 vacías, 1 "Buenos Aires" | Usar la coordenada. |
| Unidades y tipos sin normalizar | "GR"/"gr"/"gr."/"grm", "Supermercado"/"supermercado" | Normalizar en staging (etapa 4). |

## Pendiente de verificar

- **Acceso desde GitHub Actions:** falta confirmar que el servidor no bloquea IPs del exterior. Se prueba con
  un workflow manual al empezar la etapa 3. Si lo bloquea, la alternativa es un runner propio o descargar desde una PC.
## Estabilidad entre días (primeros 7 días, 12 al 18/11/2026)

La primera corrida de la ingesta recuperó los 7 paquetes disponibles. Esto es lo que se vio:

- **Hay cadenas enteras que faltan algunos días.** Su zip directamente no viene en el paquete:
  - 12/11: falta **Cencosud** (Vea, Disco, Jumbo).
  - 18/11: falta **Farmacity/Simplicity**.
- El comercio 36 vino vacío y el 47 desactualizado **los 7 días**.
- Fuera de esas ausencias, la cantidad de sucursales por bandera es estable de un día a otro.
- Cada día procesado ocupa entre 15 y 17 MB en Parquet.

Consecuencias:
- **Etapa 2:** el control de "cadena que dejó de informar" es necesario, pero tiene que ser una **advertencia**, no un error: pasa seguido y no es un problema de la ingesta.
- **Etapa 4:** una comparación diaria entre cadenas no puede asumir que todas están todos los días. Hay que decidir si se usa el último precio conocido (con un máximo de días) o si se comparan solo los días en que están todas.
