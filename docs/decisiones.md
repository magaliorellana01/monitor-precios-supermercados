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

## 5. Almacenamiento: los datos diarios fuera de git *(confirmada el 18/11/2026; implementada en la etapa 3)*

**Decisión:**
- **Los Parquet diarios** (precios, sucursales, comercios y productos de CABA + GBA, ~17 MB por día en total) se guardan como
  **archivos adjuntos de Releases de GitHub**, con la forma `precios_2026-11-18.parquet`. No pesan en el repo y se pueden bajar con una URL.
- **Un Release por mes** (`datos-2026-11`): GitHub admite como máximo 1000 archivos por Release, y con 4 tablas por día
  un solo Release alcanzaría para 250 días. Un mes son 124 archivos.
- **En el repo** van los logs (`data/ingesta/log_ingesta.csv` y `data/calidad/log_calidad.csv`) y, más adelante, solo las tablas chicas
  que usan el dashboard y el reporte (canasta, índice, métricas), que se regeneran en cada corrida.
- La subida y la bajada están en `src/almacen.py`.

**Por qué:** guardar el detalle en git sumaría unos 6 GB por año, y cada commit de datos queda para siempre en el historial.
Hasta la versión agregada por bandera y producto llega a 1 GB por año. GitHub recomienda repos de menos de 1 GB.

**Crecimiento medido (primeros 7 días):**

| Dónde | Por día | Por año |
|---|---|---|
| Repo (los dos logs) | ~1,5 KB | ~0,5 MB |
| Releases (Parquet) | ~17 MB | ~6,2 GB |

Los Releases no tienen un tope de espacio total (sí de 2 GB por archivo, muy lejos de los 17 MB).

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

---

## 8. Limpieza de precios: qué se descarta antes de guardar

**Decisión:** antes de guardar un día se descartan, en `sql/ingesta/04_precios.sql`, las filas con:

| Motivo | Regla |
|---|---|
| `precio_vacio` | `productos_precio_lista` vacío o no numérico. |
| `precio_cero_o_negativo` | Precio de lista menor o igual a cero. |
| `duplicado` | Misma sucursal y producto repetidos: se guarda una sola fila, la de menor precio válido. |
| `precio_absurdo` | Más de 100 veces o menos de 1/100 de la **mediana del producto** ese día. |

La mediana se calcula por EAN entre todas las cadenas. Para los códigos internos (`productos_ean = 0`), que
solo son únicos dentro de un comercio, se calcula por comercio y código.

**Por qué:**
- El plan sugería un tope fijo, pero en la etapa 0 vimos que 332 precios superan los 5 millones y la mayoría son
  televisores y otra electrónica. Con un tope fijo se descartarían precios reales. Comparar contra la mediana del propio producto separa los dos casos.
- Con datos reales (12 al 18/11/2026) se descartan entre 117 y 191 filas por día, menos del 0,003% de lo guardado.
  Las 117 "absurdas" son siempre las mismas: un producto de la Cooperadora Deheza (comercio 3) a $0,01 contra una mediana de $6.349.
- Se descarta en lugar de corregir: no hay forma de saber cuál es el precio correcto.

**Descartado:**
- *Tope fijo de precio:* descarta electrónica real.
- *Detectar valores extremos con desvío estándar o rangos intercuartílicos:* con pocos precios por producto (muchos están en una sola cadena) se vuelve inestable. Con la mediana alcanza y se explica en una línea.
- *Descartar los productos de una sola sucursal:* no tienen mediana contra la que comparar, pero un precio solo no es sospechoso por eso. Esos precios se guardan.

**Limitación:** un producto informado en una sola sucursal nunca se marca como absurdo, porque la mediana es él mismo.

---

## 9. Controles de calidad: umbrales y qué frena el proceso

**Decisión:** los controles dan tres resultados. Los umbrales están en `src/calidad.py` y la tabla completa en el README.

- **Error grave:** el día no se guarda y el comando termina con código de salida 1. Se reserva para lo que
  indica que los datos no sirven: cambió el formato (faltan columnas), el archivo es viejo o no es del día que dice, el día queda
  sin precios, más del 1% de precios inválidos, duplicados o absurdos, más del 5% de precios de sucursales que no existen,
  más del 20% de las sucursales sin precios, una caída de filas de más del 30% frente al día anterior, o un portal sin datos de hoy ni de ayer.
- **Advertencia:** el día se guarda y el aviso queda en `data/calidad/log_calidad.csv`. Incluye una caída de filas de más del 10%,
  una cadena que informó ayer y hoy no, o una cadena que informa menos de la mitad de sus sucursales.
- Todos los resultados (también los `ok`) se registran, para poder ver cómo evolucionan.

**Por qué:**
- **Una cadena que falta es advertencia, no error.** En los primeros 7 días ya faltó Cencosud un día (12/11) y Farmacity otro (18/11).
  Frenar la ingesta cada vez dejaría días sin guardar por un problema que no es de nuestro pipeline, y el portal pisa los archivos a la semana.
- **Los umbrales salen de los datos.** La variación diaria de filas en los primeros días fue de -5,7% a +4,5%. Por eso 10% avisa y 30% frena: queda lejos del ruido normal pero detecta una descarga rota.
- **El control de columnas se corre antes que el resto.** Si falta una columna, el SQL de la ingesta ni siquiera puede ejecutarse. Este error frena incluso con `--aceptar-errores`.
- **`--aceptar-errores`** existe como salida de emergencia: si una caída de más del 30% es real (por ejemplo, un feriado), sin esta opción el pipeline fallaría todos los días y se perderían datos.
- **La fecha esperada sale del portal y no del reloj.** Un zip viejo es consistente consigo mismo (su carpeta y su metadata coinciden), así que solo
  se detecta comparando contra la fecha de publicación que informa la API y contra el día de la semana. Para el caso de que el portal directamente no
  publique, hay un control aparte (`portal_actualizado`) que compara el último paquete con la fecha de hoy en Argentina.

**Descartado:**
- *Frenar siempre ante cualquier cadena ausente:* ver arriba.
- *Que los avisos solo se muestren por pantalla:* en GitHub Actions nadie los ve. Quedan en un CSV versionado.
- *Umbrales distintos por cadena:* más precisos, pero hay que mantenerlos a mano. Se puede retomar si los avisos molestan.

**Avisos permanentes.** Hoy cuatro avisos aparecen todos los días: los dos comercios descartados (36 y 47), los 117 precios
absurdos, los 55 mil precios de sucursales que no figuran en `sucursales.csv` y unas 17 sucursales sin precios. Son problemas conocidos de la fuente
(ver `docs/fuente_sepa.md`). El valor del log está en ver cuándo **cambian**, no en que aparezcan.

---

## 10. Automatización: cuándo corre, qué pasa si falla y quién commitea

**Decisión:** el workflow `.github/workflows/descarga_diaria.yml` corre todos los días a las **18:00 UTC (15:00 en Argentina)**
y también a mano (`workflow_dispatch`). En cada corrida:

1. Verifica que el portal responda (`--verificar-acceso`).
2. Baja de los Releases los últimos 10 días, para saber qué días ya están guardados y poder comparar contra el día anterior.
3. Corre la ingesta: procesa solo los días que faltan, con sus controles de calidad.
4. Sube los días nuevos al Release del mes.
5. Commitea los dos logs, aunque la ingesta haya fallado: así el motivo del error queda registrado.
6. Si la ingesta falló, marca la corrida como fallida y GitHub avisa por mail.

**Por qué:**
- **15:00 y no a las 13:30.** El portal publica el zip del día alrededor de las 13:20, y GitHub puede demorar una corrida programada hasta una hora
  cuando hay mucha carga. A las 15:00 el archivo ya está y queda margen.
- **Un solo horario.** Como el portal guarda 7 días y la ingesta es idempotente, si una corrida falla la del día siguiente recupera el día perdido.
  Una segunda corrida diaria no suma nada.
- **Bajar los últimos días en cada corrida.** Un runner de GitHub empieza sin archivos. Sin esto procesaría de nuevo los 7 días
  disponibles todos los días (~10 minutos y más de 120 MB subidos), y los controles no tendrían un día anterior contra el cual comparar.
- **Los tests no están en este workflow.** Un test roto no debe detener la recolección de datos, porque el portal no guarda historial. Corren en
  otro workflow (`tests.yml`), en cada Pull Request.
- **Commit diario de los logs.** Cada corrida agrega la fila `portal_actualizado` al log de calidad, así que siempre hay un commit. Eso evita que GitHub desactive el workflow
  programado por 60 días sin actividad (aplica a repos públicos).
- **Memoria.** Procesar un día ocupa un pico de 3,7 GB de RAM. Entra en los runners de GitHub (7 GB en repos privados, 16 GB en públicos).

**Descartado:**
- *Commitear los Parquet* (plan original): ver decisión 5.
- *Un runner propio (self-hosted) en esta PC:* solo hace falta si el servidor del portal bloquea las IP de GitHub. Habría que dejar la PC prendida todos los días. Se prueba primero la opción sin runner propio.
- *Subir los Parquet como artefactos del workflow:* GitHub los borra a los 90 días como máximo.
