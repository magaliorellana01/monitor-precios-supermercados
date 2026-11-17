# Decisiones metodológicas

Cada decisión registra qué se decidió, por qué y qué alternativas se descartaron.

---

## 1. Fuente: portal de origen y API CKAN

**Decisión:** descargar desde `datos.produccion.gob.ar` y obtener la URL de cada día con la API CKAN
(`package_show?id=sepa-precios`), buscando el recurso cuyo nombre es el día de la semana.

**Por qué:** el espejo de datos.gob.ar mostraba fechas de julio cuando el origen ya estaba en noviembre.
Si se buscan las URLs por la API, el pipeline sigue funcionando aunque el portal cambie los ids de los recursos.

**Descartado:** usar las URLs fijas del espejo de datos.gob.ar.

---

## 2. Fecha de los datos: la de la carpeta interna del zip

**Decisión:** la fecha de un paquete es la de su carpeta interna (`AAAA-MM-DD/`). Si un comercio trae CSVs con
más de 2 días de diferencia respecto de esa fecha, sus datos se descartan ese día.

**Por qué:** el nombre del archivo (`sepa_lunes.zip`) no dice de qué semana es, y `comercio_ultima_actualizacion`
es incorrecta en algunos comercios (Changomas declara 2017). El comercio 47 republica todos los días datos de 2025.

**Descartado:** usar la fecha de descarga o el campo `comercio_ultima_actualizacion`.

---

## 3. Zona: CABA + GBA por distancia al Obelisco

**Decisión:** guardar las sucursales que cumplen alguna de estas dos condiciones:
- provincia `AR-C` (CABA), o
- están a **40 km o menos del Obelisco** (-34.6037, -58.3816).

Para el análisis se usan dos zonas: **CABA** (provincia `AR-C`) y **GBA** (el resto dentro de los 40 km).

**Por qué:**
- Es la zona con más sucursales (unas 1.700 de 3.000) y donde compiten todas las cadenas grandes, así que se
  pueden comparar cadenas **dentro de la misma zona**.
- La localidad es texto libre y no sirve (418 sucursales de provincia dicen "BUENOS AIRES"). Las coordenadas están completas.
- 40 km cubren aproximadamente los 24 partidos del conurbano.

**Descartado:**
- *Todo el país:* 35 MB por día y mezcla mercados muy distintos. Se puede retomar más adelante.
- *Solo CABA:* más chico, pero deja afuera Changomas y gran parte de Carrefour Maxi y Coto, que tienen sucursales en el conurbano.
- *Filtrar por localidad o por los polígonos de los partidos:* la localidad no es confiable, y los polígonos agregan una dependencia geográfica por una diferencia marginal.

---

## 4. Productos: guardar todos los de la zona

**Decisión:** guardar todos los productos de las sucursales de la zona, sin recortar.

**Por qué:** la canasta (etapa 4) y la prima de marca necesitan elegir productos con datos ya acumulados.
Si se recorta antes, se pierden historias que el portal no guarda. Recortar a los productos en 3 o más comercios solo
reduce el tamaño a la mitad (de 15 a 7 MB por día), así que no cambia la decisión de dónde guardar los datos.

**Descartado:** guardar solo los productos de la canasta o solo los que están en 3 o más comercios.

---

## 5. Almacenamiento: los datos diarios fuera de git *(propuesta, a confirmar en la etapa 3)*

**Decisión propuesta:**
- **Detalle diario** (precios por sucursal y producto de CABA + GBA, ~15 MB por día en Parquet zstd) → se guarda como
  **archivo adjunto de un Release de GitHub**, un archivo por día. No pesa en el repo y se puede bajar con una URL.
- **Tablas de productos y sucursales** → también en el Release, actualizadas en cada corrida.
- **En el repo** → solo las tablas chicas que usan el dashboard y el reporte (canasta, índice, métricas), que se regeneran en cada corrida.

**Por qué:** guardar el detalle en git sumaría unos 5,5 GB por año, y cada commit de datos queda para siempre en el historial.
Hasta la versión agregada por bandera y producto llega a 1 GB por año. GitHub recomienda repos de menos de 1 GB.

**Descartado:**
- *Commitear los Parquet diarios* (lo que planteaba el plan original): el repo se vuelve inmanejable en pocos meses.
- *Git LFS:* la cuota gratuita (1 GB de almacenamiento y 1 GB de transferencia por mes) no alcanza.
- *Almacenamiento en la nube (S3, R2, Hugging Face):* funciona, pero suma cuentas y credenciales que no hacen falta para este volumen.

---

## 6. Precio principal: `productos_precio_lista`

**Decisión:** las métricas de precio usan `productos_precio_lista`. Las promociones se guardan aparte y solo se
analizan para los comercios que las informan.

**Por qué:** es el único precio obligatorio y comparable: el que paga cualquier consumidor sin descuentos.
Las promociones se informan de forma muy desigual (DIA el 22%, la mitad de los comercios nunca).

**Descartado:** usar el menor precio entre lista y promo, porque la comparación entre cadenas favorecería a las que informan promociones.

---

## 7. Identificador de producto: EAN

**Decisión:** para comparar entre cadenas se usan solo productos con `productos_ean = 1`, identificados por `id_producto`.

**Por qué:** el EAN es el mismo código en todas las cadenas, y el 99% de las filas lo tiene. Los códigos internos
(`productos_ean = 0`) solo sirven dentro de un comercio.

**Descartado:** emparejar productos por descripción, que es texto libre y distinto en cada cadena.
