# Monitor de precios de supermercados

> **Proyecto en construcción.** Por ahora estoy en la etapa de reconocimiento de la fuente de datos.

Este proyecto descarga todos los días los precios que los supermercados de Argentina informan a la base **SEPA** (Precios Claros, [datos.gob.ar](https://datos.gob.ar)). Con esos datos arma su propio historial y controla su calidad. Después los modela en DuckDB y publica un dashboard y un reporte semanal que se actualizan solos.

El portal publica los precios del día pero no guarda el historial. Por eso este monitor tiene que descargarlos todos los días: un día que no se descarga es un día de datos que se pierde.

## Preguntas que busca responder

1. ¿Cuánto cambia el precio del mismo producto según la cadena y la zona?
2. ¿En qué cadena sale más barata una canasta de productos básicos y cuánto se ahorra frente a la más cara?
3. ¿Cuánto más se paga por la marca líder frente a la segunda marca o la marca propia?
4. ¿Cómo cambian los precios semana a semana y cómo se comparan con el IPC del INDEC?
5. ¿Las promociones son reales o el precio "de oferta" es el precio de siempre?

## Cómo funciona

```mermaid
flowchart LR
    A[SEPA<br/>datos.gob.ar] -->|descarga diaria| B[Ingesta<br/>y filtro por zona]
    B --> C{Controles<br/>de calidad}
    C -->|ok| D[(Parquet<br/>por fecha)]
    C -->|error grave| X[Falla el workflow]
    D --> E[Modelo SQL<br/>DuckDB]
    F[IPC INDEC<br/>ArgentinaDatos] --> E
    E --> G[Dashboard<br/>Streamlit]
    E --> H[Reporte<br/>semanal]
```

## Stack

| Para qué | Herramienta |
|---|---|
| Descarga y orquestación | Python |
| Transformaciones y métricas | DuckDB y SQL |
| Almacenamiento | Parquet particionado por fecha |
| Automatización | GitHub Actions |
| Dashboard | Streamlit |
| Inflación oficial | API de ArgentinaDatos (IPC del INDEC) |

## Criterios metodológicos

- Para los precios uso **medianas** y no promedios, para que un valor extremo no distorsione el resultado.
- Los rankings solo incluyen casos con un **mínimo de observaciones**.
- Al comparar cadenas **controlo por zona**, para no confundir una cadena cara con una cadena que tiene sucursales en barrios caros.
- La canasta tiene una **composición fija**, así que el índice propio mide el cambio de precios y no un cambio en los productos.
- Cada decisión queda documentada en `docs/decisiones.md`, con las alternativas que descarté.

## Estado

- [x] Etapa 0: reconocimiento de la base SEPA ([documentación de la fuente](docs/fuente_sepa.md))
- [x] Etapa 1: pipeline de descarga
- [x] Etapa 2: controles de calidad
- [ ] Etapa 3: automatización con GitHub Actions
- [ ] Etapa 4: modelo de datos en SQL
- [ ] Etapa 5: análisis
- [ ] Etapa 6: dashboard
- [ ] Etapa 7: reporte semanal automático

## Limitaciones conocidas

- Son los precios que **informan las cadenas**, no precios de tickets reales.
- Solo están las cadenas obligadas a informar a SEPA, que son las más grandes.
- El historial empieza el día en que arrancó la descarga automática.
- Si la fuente cambia de formato, el pipeline puede romperse. Los controles de calidad están para detectarlo.

## Cómo correrlo en local

Requiere Python 3.11 o más nuevo.

```bash
python -m venv .venv
.venv\Scripts\activate          # en Linux o macOS: source .venv/bin/activate
pip install -r requirements.txt

python -m src.ingesta           # descarga y guarda los días disponibles que falten (hasta 7)
```

Otras opciones:

| Comando | Qué hace |
|---|---|
| `python -m src.ingesta --dia lunes` | Procesa solo el paquete de ese día de la semana. |
| `python -m src.ingesta --archivo sepa_lunes.zip` | Procesa un zip ya descargado. |
| `python -m src.ingesta --forzar` | Reprocesa aunque la fecha ya esté guardada. |
| `python -m src.ingesta --aceptar-errores` | Guarda el día aunque los controles de calidad den error grave. |
| `python -m pytest` | Corre los tests. |

Cada día procesado queda en `data/<tabla>/fecha=AAAA-MM-DD/<tabla>.parquet` (precios, sucursales, comercios y productos),
y el resumen de cada corrida en `data/ingesta/log_ingesta.csv`.

### Controles de calidad

Antes de guardar cada día se corren 13 controles (`src/calidad.py` y `sql/calidad/`). Su resultado queda en
`data/calidad/log_calidad.csv`, con la columna `resultado` en `ok`, `advertencia` o `error`.

- **Error grave:** el día no se guarda y el comando termina con código de salida 1 (así GitHub Actions marca la corrida como fallida).
- **Advertencia:** el día se guarda y el aviso queda registrado.

| Control | Qué detecta | Advertencia | Error |
|---|---|---|---|
| `columnas_faltantes` | El formato de los CSV cambió | | cualquier columna |
| `fecha_paquete` | Archivo viejo o fecha distinta a la del portal | | sí |
| `portal_actualizado` | El portal no publicó datos de hoy ni de ayer | | más de 1 día |
| `comercios_descartados` | Zip vacío o con datos viejos | cualquiera | |
| `sin_precios` | El día quedó sin ningún precio | | sí |
| `precios_invalidos` | Precios vacíos, cero o negativos | cualquiera | más del 1% de las filas |
| `duplicados` | Misma sucursal y producto repetidos | cualquiera | más del 1% |
| `precios_absurdos` | Más de 100 veces (o menos de 1/100) de la mediana del producto | cualquiera | más del 1% |
| `precios_sin_sucursal` | Precios de sucursales que no figuran en `sucursales.csv` | cualquiera | más del 5% |
| `sucursales_sin_precios` | Sucursales de la zona sin ningún precio | cualquiera | más del 20% |
| `banderas_sin_comercio` | Precios de una bandera que no figura en `comercio.csv` | cualquiera | |
| `variacion_filas` | Caída de filas frente al último día guardado | más del 10% | más del 30% |
| `banderas_ausentes` | Cadenas que informaron el día anterior y hoy no | cualquiera | |
| `caida_sucursales_bandera` | Cadenas que informan menos de la mitad de sus sucursales | cualquiera | |

Los precios inválidos, duplicados y absurdos se descartan antes de guardar. El criterio completo está en `docs/decisiones.md` (decisiones 8 y 9).

### Automatización

El workflow [`descarga_diaria.yml`](.github/workflows/descarga_diaria.yml) corre todos los días a las 15:00 (hora argentina)
y también se puede lanzar a mano desde la pestaña *Actions*. En cada corrida baja el día, lo controla y lo guarda.

Dónde queda cada cosa:

| Qué | Dónde |
|---|---|
| Parquet diarios (~17 MB por día) | Archivos de un Release por mes: `datos-2026-11`, `datos-2026-12`... |
| Logs de ingesta y de calidad | En el repo, commiteados por el workflow |

Si algo falla (error de calidad, portal sin datos, descarga rota), la corrida queda en rojo y GitHub avisa por mail.
Para recibir el aviso: *Settings → Notifications → Actions* y activar *Send notifications for failed workflows only*.

Comandos para trabajar con los Releases desde tu PC (requieren la [CLI de GitHub](https://cli.github.com) y `gh auth login`):

| Comando | Qué hace |
|---|---|
| `python -m src.almacen subir` | Sube a los Releases los días de `data/` que falten. |
| `python -m src.almacen subir --forzar` | Reemplaza lo ya subido (por ejemplo, tras reprocesar un día). |
| `python -m src.almacen bajar --dias 10` | Baja los últimos días que no estén en `data/`. |
| `python -m src.ingesta --verificar-acceso` | Prueba que se pueda llegar al portal. |

Los workflows instalan solo `requirements-pipeline.txt` (DuckDB y pytest). El resto de `requirements.txt` es para los notebooks.
