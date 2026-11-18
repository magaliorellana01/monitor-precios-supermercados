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
- **Los logs** (`log_ingesta.csv` y `log_calidad.csv`) van en un Release aparte, `datos-logs`, que se reemplaza en cada corrida.
- **En el repo** quedan solo el código y, más adelante, las tablas chicas que usan el dashboard y el reporte (canasta, índice, métricas).
- La subida y la bajada están en `src/almacen.py`.

**Por qué:** guardar el detalle en git sumaría unos 6 GB por año, y cada commit de datos queda para siempre en el historial.
Hasta la versión agregada por bandera y producto llega a 1 GB por año. GitHub recomienda repos de menos de 1 GB.

**Crecimiento medido (primeros 7 días):**

| Dónde | Por día | Por año |
|---|---|---|
| Repo | nada (ni Parquet ni logs) | nada |
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
  una cadena que informó ayer y hoy no, una cadena que informa menos de la mitad de sus sucursales, o días sin datos entre este y el último día guardado.
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
- *Que los avisos solo se muestren por pantalla:* en una ejecución automática nadie los ve. Quedan en un CSV (que se sube al Release `datos-logs`).
- *Umbrales distintos por cadena:* más precisos, pero hay que mantenerlos a mano. Se puede retomar si los avisos molestan.

**Avisos permanentes.** Hoy cuatro avisos aparecen todos los días: los dos comercios descartados (36 y 47), los 117 precios
absurdos, los 55 mil precios de sucursales que no figuran en `sucursales.csv` y unas 17 sucursales sin precios. Son problemas conocidos de la fuente
(ver `docs/fuente_sepa.md`). El valor del log está en ver cuándo **cambian**, no en que aparezcan.

---

## 10. Automatización: la ejecución diaria corre en la PC, no en GitHub Actions

**Decisión:** la ejecución diaria corre en la PC con el **Programador de tareas de Windows**, todos los días a las 15:00.
El script `scripts/tarea_diaria.ps1` lanza `python -m src.diaria`, que:

1. Baja de los Releases lo que falte en `data/` (útil si se cambia de PC).
2. Corre la ingesta: descarga los días nuevos, los controla y los guarda.
3. Sube los días nuevos y los logs a los Releases (`datos-AAAA-MM` y `datos-logs`).

Si algo falla, termina con código 1, **sube igual lo que haya salido bien y los logs** (con el motivo del error) y muestra una
ventana de aviso en pantalla. El detalle queda en `data/ingesta/ultima_ejecucion.log`. La tarea se registra una vez con
`scripts/registrar_tarea.ps1`. GitHub Actions se usa solo para correr los tests en cada Pull Request (`tests.yml`).

**Por qué no GitHub Actions:** el plan original era un workflow diario. El 18/11/2026 se probó y **el servidor del portal
(`datos.produccion.gob.ar`) responde HTTP 403 a los runners de GitHub**, ya en la primera consulta, la de la API.
Se repitió la prueba con un User-Agent de navegador y dio lo mismo: es un bloqueo por IP, no por cómo se identifica el programa.
Desde una conexión común de Argentina funciona.

**Por qué no pasa nada si la PC no está siempre prendida:**
- El portal guarda **7 días**, así que se puede tener la PC apagada hasta 6 días seguidos sin perder datos: la siguiente corrida baja los días que faltan.
- La tarea se registra con "correr apenas se pueda si se perdió la hora": si la PC estaba apagada a las 15:00, corre cuando se prende.
- El control `dias_sin_datos` deja una advertencia en el log si entre el último día guardado y el nuevo hay un hueco.
- Lo único que no se recupera es una pausa de más de 7 días. El portal no guarda historial.

**Por qué los logs no van en git:** la tarea corre dentro de la carpeta de trabajo, donde también se editan ramas.
Si commiteara los logs dejaría cambios sin guardar y ensuciaría cada rama. Los logs se guardan en el Release `datos-logs`, donde se
reemplazan en cada corrida (el historial de los primeros días quedó en el historial de git).

**Descartado:**
- *Un runner propio de GitHub (self-hosted) en esta PC:* tiene la misma dependencia de que la PC esté prendida que la tarea programada, y suma un servicio permanente que mantener.
- *Un servidor propio o un servicio en la nube (VPS, funciones serverless):* la mayoría usa IP de centros de datos y es probable que reciban el mismo 403. Además suman costo y cuentas.
- *Pedirle al portal que desbloquee las IP de GitHub:* no hay un canal para eso y no depende de este proyecto.
- *Commitear los logs desde la tarea:* ver arriba.

**Cómo se volvería a GitHub Actions:** si el portal deja de bloquear las IP de GitHub, el workflow original está en el historial de git
(Pull Request #4). El acceso se puede probar con `python -m src.ingesta --verificar-acceso` desde un workflow manual.

---

## 11. Estructura del modelo: cuatro capas, carga incremental y detalle acotado

**Decisión:** el modelo está en `data/modelo.duckdb` y se arma con `python -m src.modelo`, que corre los SQL de `sql/` en este orden:

| Capa | Qué hace |
|---|---|
| `01_staging` | Vistas temporales sobre los Parquet y los archivos de `config/`. No se guardan en el modelo. |
| `02_dimensiones` | `dim_fecha`, `dim_cadena`, `dim_sucursal`, `dim_producto`, `dim_canasta`, `dim_par_marca` y `parametros`. |
| `03_hechos` | `fct_precios` (sucursal, producto y día), `fct_precio_representativo` y `fct_cobertura_dia`. |
| `04_metricas` | Canasta, ranking, índice, dispersión y prima de marca. Se recalculan enteras en cada corrida. |

- **Incremental:** los archivos de `03_hechos` se ejecutan una vez por cada día nuevo (con `{{FECHA}}`), no con todo el historial.
  Un día se vuelve a cargar si su Parquet cambió después de cargarlo (se reprocesó), y cada día se carga en una transacción para que nunca quede a medias.
- **Claves naturales**, sin claves inventadas: `id_comercio + id_bandera + id_sucursal` y `clave_producto`. Una clave numérica generada con `dense_rank` cambiaría cuando aparecen
  sucursales nuevas y rompería la carga incremental, y un hash puede cambiar entre versiones de DuckDB.
- **`clave_producto`** es el EAN. Los códigos internos de un comercio (`productos_ean = 0`) llevan el comercio adelante (`c12-0000000000001`) para que no se mezclen con los de otra cadena.
- **Los hechos de precios son solo de productos con EAN**: son los únicos comparables entre cadenas.
- **El detalle por sucursal se conserva 60 días** (`retener_dias_fct_precios`). Medido: un día ocupa 43 MB en DuckDB (con los datos ordenados por producto; sin ordenar eran 63 MB)
  contra 17 MB en Parquet. Conservar todo serían unos 15 GB por año en la PC, y nada de lo planeado usa el detalle por sucursal de hace meses. La historia de largo plazo queda en
  `fct_precio_representativo` (unas 410 mil filas por día) y los Parquet completos siguen en `data/precios/` y en los Releases.
- **Las dimensiones que se leen enteras (`dim_sucursal`, `dim_cadena`) son chicas;** `dim_producto` se actualiza con una ventana de 14 días porque leer todas las descripciones de todos los días no escala.

**Descartado:**
- *Que las vistas de staging queden guardadas:* dejarían rutas absolutas dentro de `modelo.duckdb`, y el archivo dejaría de servir en otra PC.
- *Reconstruir todo el modelo en cada corrida:* son 26 segundos con 7 días, pero crece con el historial. La corrida incremental sin días nuevos tarda 2 segundos.
- *Guardar el detalle por sucursal sin límite:* ver arriba.
- *Agregar con `count(distinct ...)` sobre todos los precios:* falló por memoria con 52 millones de filas. Las agregaciones se hacen por día y en un solo paso.

---

## 12. Qué es una "cadena", una "zona" y una cadena "comparable"

**Decisión:** la cadena se define en `config/cadenas.csv`, bandera por bandera:
- **Changomas** junta sus tres banderas (Changomas, SuperChangomas, HiperChangomas).
- **Carrefour queda separado por formato** (Hipermercado, Market, Express y Maxi), igual que Cencosud (Vea, Disco y Jumbo).
- Cada cadena tiene un **rubro**: `supermercado`, `farmacia` o `tienda_de_conveniencia`. Farmacity y Simplicity son farmacias. Los comercios 3, 4 y 23 (Deheza, Estación Lima y Axion,
  de entre 175 y 255 productos cada uno) son tiendas de estaciones de servicio y de autopista.
- Las zonas son **CABA**, **GBA** y **TODAS** (CABA y GBA juntas). La mediana de TODAS no se puede sacar de las otras dos, así que se calcula aparte.
- Una cadena es **comparable** si es un supermercado y tiene **al menos 5 sucursales en esa zona** (`min_sucursales_cadena`). Solo las cadenas comparables entran en rankings, índices y dispersión.

**Por qué:**
- Un Carrefour Express y un Carrefour Hipermercado tienen precios distintos. Si fueran una sola cadena, su mediana sería casi la de los Express (unas 420 de las 515 sucursales de Carrefour en la zona) y se confundiría "Carrefour caro"
  con "Carrefour está en barrios caros". Es el mismo criterio de controlar por zona.
- La Anónima y la Cooperativa Obrera tienen **2 sucursales cada una** en la zona. Con tan pocos casos, quedarían como "la más barata" o "la más cara" por azar.
- Una bandera que no está en el archivo queda con rubro `sin_clasificar` y el modelo avisa al terminar, para que aparezca sola cuando el portal sume una cadena.

**Descartado:**
- *Cadena = empresa (`id_comercio`):* mezcla Carrefour Express con Hipermercado y Vea con Jumbo.
- *Agregar zonas más finas (barrio, partido):* con 2 a 40 sucursales por cadena en la mayoría de los partidos, no alcanzan los casos.

---

## 13. La canasta: 30 productos, y qué pasa cuando falta alguno

**Decisión:** la canasta está en `config/canasta.csv` y tiene 30 productos con EAN, en cinco categorías: Almacén (15), Lácteos (3), Bebidas (3), Limpieza (4) e Higiene (5).

**Cómo se eligieron.** Con los datos de la etapa 1 se calculó en cuántas de las 12 cadenas y en cuántos de los 7 días aparece cada EAN, y se eligió a mano:
- **Que estén en las 12 cadenas** (hay 407 productos así) **los 7 días**, para que todas puedan tener la canasta completa.
- Productos básicos de **marca nacional**, con una presentación fija, uno por tipo de producto.
- **El azúcar quedó afuera:** el azúcar Ledesma de 1 kg está en 9 de las 12 cadenas, y el resto no tiene un azúcar en todas. Tampoco hay legumbres con cobertura completa.

**Regla de "canasta completa".** Una cadena entra en el ranking solo si tiene los 30 productos. Un costo con 29 productos no es comparable: es más bajo por faltar un producto y no por precio.

**Faltantes temporales: se arrastra el último precio hasta 3 días** (`max_dias_arrastre`). En los primeros 7 días hubo 3 casos aislados de uno o dos días (DIA no informó 2 productos el 17/11 y Vea
no informó el shampoo el 17 y el 18). Sin esta regla, DIA, la cadena con más sucursales, desaparecía del ranking de CABA ese día. Es lo que se hace en los índices de precios con faltantes
temporales. La tabla `m_canasta_dia` indica cuántos precios de cada día son arrastrados (`n_productos_arrastrados`). Después de 3 días sin informar, el producto cuenta como faltante.

**Limitaciones:**
- **Los precios de DIA y de las marcas propias no están reflejados:** DIA vende sobre todo marca propia, y la canasta es de marcas nacionales. Mide lo que paga quien compra esas marcas en cada cadena.
- Una cadena de formato chico (Carrefour Express, DIA) puede tener la canasta completa y aun así ofrecer menos variedad. El ranking compara precios, no surtido.
- La canasta se revisa a mano. Si un producto desaparece de una cadena, el modelo lo avisa (`productos de la canasta sin ningún precio`).

**Descartado:**
- *Una canasta por listas oficiales (CBA, Precios Cuidados):* no se pueden emparejar con los EAN de SEPA sin trabajo manual, y no cubren higiene ni limpieza.
- *Elegir por ventas:* SEPA no informa ventas, solo precios.
- *Aceptar canastas casi completas (por ejemplo 27 de 30):* cambia el costo según qué productos falten y vuelve incomparables a las cadenas.

---

## 14. Precio representativo e índice propio

**Decisión:**
- **Precio representativo:** la **mediana** del precio de lista (`productos_precio_lista`, sin promociones) de un producto entre las sucursales de una cadena, por día y zona.
  Una sucursal con un error de carga o ubicada en un barrio caro no mueve la mediana.
- **Costo de la canasta:** la suma de los precios representativos de los 30 productos, **una unidad de cada uno**.
- **Índice:** el costo de la canasta de la cadena relativo a su costo el día base, por 100. Vale 100 el **13/11/2026** (`fecha_base_indice`), el primer día con las 12 cadenas
  (el 12/11 faltó Cencosud). La composición es fija: siempre los mismos productos, así que el índice mide solo variación de precios.
- **Índice general:** la **mediana de los índices de las cadenas** de ese día. Con la mediana, que una cadena falte un día mueve poco el resultado.

**Por qué:**
- No hay datos de consumo, así que no se puede ponderar por gasto. Una unidad de cada producto es una ponderación igual, simple y explicable. Es la limitación
  principal del índice: no representa el gasto real de un hogar.
- Se usa el precio de lista y no el promocional, porque solo DIA y la Cooperativa Obrera informan promociones (ver `docs/fuente_sepa.md`) y favorecería a las que más las informan.

**Primeros resultados (7 días, no son conclusiones):** el índice se mueve entre 99,0 y 100,3: los precios casi no cambiaron en la semana. Hasta que haya varias semanas de historia el índice no dice nada.
Las diferencias entre cadenas sí son grandes: la misma canasta cuesta un 17,7% más en Disco que en Carrefour Maxi, y los productos de la canasta con más dispersión cuestan entre un 32% y un 47% más en la cadena
más cara que en la más barata.

**Descartado:**
- *Índice con ponderaciones de gasto (Laspeyres con la canasta del INDEC):* no hay forma de emparejar las categorías del INDEC con los productos de SEPA.
- *Índice encadenado, que compara solo los productos presentes en dos días seguidos:* es más robusto a faltantes, pero con una canasta de 30 productos y el arrastre de precios no hace falta, y es más difícil de explicar.
- *Promedio en lugar de mediana:* un precio mal cargado mueve el resultado.

---

## 15. Prima de marca: líder contra alternativa, dentro de la misma cadena

**Decisión:** en `config/marcas.csv` hay pares de productos de **la misma categoría y presentación**: uno **líder** y uno **alternativo**, que son otra marca nacional. Seis pares: aceite de girasol 900 cc, leche entera en sachet de 1 L,
yerba mate de 1 kg, detergente de 500 ml, jabón líquido para ropa de 800 cc y crema dental de 90 g. La prima es `precio del líder / precio de la alternativa - 1`, **dentro de la misma cadena y el mismo día**.
Solo hay prima si la cadena vende los dos productos ese día.

**Por qué comparar dentro de la cadena:** el precio de las dos marcas está en la misma góndola, así que la diferencia no se mezcla con que una cadena sea más cara que otra.

**Limitaciones:**
- **El "líder" lo define el criterio de quien arma el archivo** (la marca más conocida de cada categoría), porque SEPA no informa ventas ni participación de mercado. Por eso la prima puede ser **negativa**:
  Cocinero cuesta un 7% menos que Natura. Es un dato, no un error del cálculo.
- Seis pares son pocos. Las conclusiones por categoría se limitan a esas categorías.
- Algunas alternativas pueden ser otra marca de la misma empresa que el líder (por ejemplo, ALA y Skip son de Unilever). Es la "segunda marca" del plan, pero no necesariamente la de un competidor.

**Descartado:**
- **Marcas propias** (Carrefour Classic, DIA, Coto, HG de Changomas, Primer Precio de la Cooperativa). Es la comparación más interesante, pero no se pudo resolver en esta etapa: cada cadena tiene sus propias marcas y sus EAN
  son distintos, SEPA no trae categoría, y hay que emparejar a mano producto por producto y cadena por cadena. Por ejemplo, para el aceite de girasol de 900 cc solo hay un equivalente
  identificable en Carrefour y en La Anónima. Queda para una segunda vuelta, y la estructura de `marcas.csv` ya admite agregar esos pares.
- **Papel higiénico** (Higienol contra Elite): se probó y se sacó, porque Elite cuesta el doble y no es un producto equivalente.
- **Comparar precio por unidad de medida** para emparejar presentaciones distintas: el contenido de `dim_producto` no es confiable cuando varias cadenas informan "1 unidad" para todo.

---

## 16. Análisis: qué se compara, con qué mínimos y cómo se miden las promociones

**Decisión:** el análisis (`notebooks/01_analisis.ipynb`) no calcula nada: corre las consultas de `sql/05_analisis/` sobre las métricas del modelo, una por pregunta, y las grafica.
- **Dispersión por producto:** mediana de los días del rango entre la cadena más cara y la más barata, solo productos de la canasta y solo si al menos 5 cadenas los comparan (`min_cadenas_dispersion`).
- **Cadenas y zonas:** el mismo criterio de la decisión 12. Se compara la misma cadena entre CABA y GBA para ver si la zona cambia el precio.
- **Prima de marca:** mediana entre cadenas y días, solo para categorías con al menos 5 cadenas.
- **IPC:** se baja con `python -m src.ipc` desde la API de ArgentinaDatos a `data/externos/ipc.csv` (fuera de git, se vuelve a bajar). Es mensual, así que la comparación con el índice propio necesita al menos un mes de historia y por ahora solo se muestra el contexto.
- **Promociones:** se mira solo la promoción general (promo1) menor al precio de lista, en cadenas con al menos 1.000 filas en promoción el último día. La **promoción permanente** es un producto en una sucursal que estuvo en promoción todos los días en que se lo observó, con al menos 3 días observados. Se calcula sobre los productos que estuvieron en promoción algún día.

**Por qué:**
- Las consultas en SQL y no en pandas, como el resto del proyecto, para que cualquier gráfico del dashboard (etapa 6) y del reporte (etapa 7) pueda reutilizarlas.
- Los mínimos evitan sacar conclusiones de un puñado de casos (Cooperativa Obrera y La Anónima quedan fuera del análisis de promociones por eso).
- "Promoción permanente" es una aproximación: con 7 días de historia no se puede distinguir una oferta larga de un precio de lista disfrazado. Cuando haya más semanas se podrá mirar si la lista sube cuando entra la promoción.

**Qué se encontró (7 días, no son conclusiones definitivas):**
- La misma cadena cobra igual en CABA y en GBA (diferencia de 0 a −0,3%): lo que cambia el precio es la cadena, no la zona.
- Productos de la canasta: entre 1,6% y 47% de diferencia entre la cadena más cara y la más barata, según el producto.
- Las promociones informadas tienen descuentos medianos de 20% a 25%, y entre el 16% y el 58% de los productos en promoción la mantienen todos los días de la semana.

**Descartado:**
- *Hacer el cálculo en el notebook con pandas:* duplicaría lógica que ya está en el modelo.
- *Concluir sobre el IPC con 7 días:* el IPC es mensual y la comparación sería ruido.

---

## 17. Dashboard: una base chica en un Release, y un filtro de zona

**Decisión:** el dashboard (`app/app.py`, Streamlit) no lee el modelo: lee `dashboard.duckdb`, que arma `python -m src.exportar` con las métricas ya calculadas
(unos 3 MB con 7 días), y que la tarea diaria sube al Release `datos-dashboard`. La app usa la copia local si existe y, si no, la baja de ese Release y la renueva cada hora.
- **Contenido:** las tablas `m_*` que muestra, `dim_canasta`, `dim_par_marca`, el precio por cadena de los productos de la canasta, el IPC y una tabla `meta` con la fecha de generación.
- **Secciones:** resumen, canasta, productos, marcas, inflación, promociones y metodología. Un solo filtro, la zona.
- **Promociones por día:** nueva métrica `m_promo_cadena_dia` (porcentaje de precios en promoción y descuento mediano por cadena y día).
  La "promoción permanente" de la decisión 16 queda solo en el notebook, porque se calcula sobre toda la ventana.

**Por qué:**
- `modelo.duckdb` pesa 425 MB y no se puede subir a git ni a Streamlit Cloud. Las métricas, que son lo que se muestra, pesan menos del 1%.
- El repositorio es público, así que la app baja el Release sin credenciales. Es el mismo mecanismo que ya usan los Parquet y los logs (decisiones 5 y 10), y la tarea diaria corre en la PC con `gh` autenticado.
- **No se commitea la base a git** para que cada actualización diaria no ensucie la historia ni el árbol de trabajo donde corre la tarea.
- La app avisa que con menos de 28 días la evolución en el tiempo y el IPC todavía no se pueden leer.

**Limitaciones:**
- El dashboard se actualiza cuando la PC corre la tarea diaria y sube el archivo; si la PC está apagada, muestra el último día subido (el pie lateral dice cuándo se generó).
- Streamlit Cloud duerme las apps sin visitas: la primera carga después de un rato puede tardar unos segundos.

**Descartado:**
- *Commitear la base a git desde la tarea diaria:* mezcla datos con código y obliga a hacer push todos los días.
- *Subir `modelo.duckdb` o los Parquet y calcular en la app:* son cientos de MB y la app tendría que repetir el modelo.
- *Un workflow de GitHub Actions que arme el dashboard:* Actions no puede descargar la fuente (decisión 10) y tampoco tiene el historial.

