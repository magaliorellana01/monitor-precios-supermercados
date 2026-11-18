# Guía técnica: cómo correr y operar el monitor

Volver al [README](../README.md). Las decisiones de diseño están en [decisiones.md](decisiones.md).

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

## Controles de calidad

Antes de guardar cada día se corren 14 controles (`src/calidad.py` y `sql/calidad/`). Su resultado queda en
`data/calidad/log_calidad.csv`, con la columna `resultado` en `ok`, `advertencia` o `error`.

- **Error grave:** el día no se guarda y el comando termina con código de salida 1 (así la tarea diaria sabe que falló y avisa).
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
| `dias_sin_datos` | Días sin datos guardados entre el último día y este (la ejecución diaria no corrió) | cualquiera | |
| `banderas_ausentes` | Cadenas que informaron el día anterior y hoy no | cualquiera | |
| `caida_sucursales_bandera` | Cadenas que informan menos de la mitad de sus sucursales | cualquiera | |

Los precios inválidos, duplicados y absurdos se descartan antes de guardar. El criterio completo está en `docs/decisiones.md` (decisiones 8 y 9).

## Automatización

La descarga diaria corre en tu PC con el **Programador de tareas de Windows**, todos los días a las 15:00. No corre en GitHub Actions porque
el portal bloquea las IP de GitHub (HTTP 403, ver `docs/decisiones.md`, decisión 10). Actions solo corre los tests en cada Pull Request.

Para dejarla funcionando (una sola vez):

1. Instalar la [CLI de GitHub](https://cli.github.com) y correr `gh auth login`.
2. Registrar la tarea, desde PowerShell en la carpeta del proyecto:

```powershell
.\scripts\registrar_tarea.ps1               # todos los días a las 15:00
.\scripts\registrar_tarea.ps1 -Hora "16:30" # otra hora
```

Cada día la tarea baja el paquete, lo controla, lo guarda, sube los Parquet a los Releases del repo y actualiza el modelo (`data/modelo.duckdb`). Si algo falla, muestra una ventana de aviso.

| Qué | Dónde |
|---|---|
| Parquet diarios (~17 MB por día) | Un Release por mes: `datos-2026-11`, `datos-2026-12`... |
| Logs de ingesta y de calidad | Release `datos-logs` (se reemplazan en cada corrida) |
| Resultado de la última ejecución | `data/ingesta/ultima_ejecucion.log` (en tu PC) |

La PC no tiene que estar prendida siempre: el portal guarda los últimos 7 días, así que podés apagarla hasta 6 días seguidos sin perder datos.
Si la tarea se perdió la hora, corre apenas la prendés.

| Comando | Qué hace |
|---|---|
| `python -m src.diaria` | Lo que hace la tarea: bajar, ingerir, subir y actualizar el modelo. |
| `Start-ScheduledTask -TaskName "Monitor precios supermercados"` | Lanza la tarea ahora. |
| `Unregister-ScheduledTask -TaskName "Monitor precios supermercados" -Confirm:$false` | La saca del Programador. |
| `python -m src.almacen subir` / `bajar --dias 10` | Sube o baja los Parquet y los logs a mano. |
| `python -m src.almacen subir-dashboard` | Sube la base del dashboard al Release `datos-dashboard`. |
| `python -m src.ingesta --verificar-acceso` | Prueba que se pueda llegar al portal. |

Los tests de GitHub instalan solo `requirements-pipeline.txt` (DuckDB y pytest). El resto de `requirements.txt` es para los notebooks.

## Modelo de datos

```
python -m src.modelo             # carga los días nuevos y recalcula las métricas (2 segundos si no hay nada nuevo)
python -m src.modelo --rehacer   # lo arma de cero con todos los días guardados (~30 segundos con 7 días)
```

Genera `data/modelo.duckdb`. Todas las transformaciones están en SQL, en la carpeta `sql/`:

| Capa | Tablas |
|---|---|
| `01_staging` | Vistas temporales sobre los Parquet y los archivos de `config/` |
| `02_dimensiones` | `dim_fecha`, `dim_cadena`, `dim_sucursal`, `dim_producto`, `dim_canasta`, `dim_par_marca`, `parametros` |
| `03_hechos` | `fct_precios` (sucursal, producto y día), `fct_precio_representativo` (mediana por cadena, zona y día), `fct_cobertura_dia` |
| `04_metricas` | `m_canasta_dia`, `m_ranking_canasta_dia`, `m_indice_cadena_dia`, `m_indice_general_dia`, `m_dispersion_producto_dia`, `m_prima_marca_dia`, `m_promo_cadena_dia` |

Los hechos son incrementales: cada día se carga una sola vez, y se vuelve a cargar si su Parquet se reprocesó.

Lo que se puede cambiar sin tocar el código está en `config/`:

| Archivo | Qué define |
|---|---|
| `cadenas.csv` | Qué es cada cadena y su rubro (supermercado, farmacia, tienda de conveniencia) |
| `canasta.csv` | Los 30 productos de la canasta, por código EAN |
| `marcas.csv` | Pares de producto líder y alternativo para la prima de marca |
| `parametros.csv` | Mínimo de sucursales para comparar cadenas, día base del índice, días de arrastre de precios y otros |

Ejemplo, el ranking de la canasta del último día:

```sql
select posicion, cadena, costo_canasta, sobre_la_mas_barata_pct
from m_ranking_canasta_dia
where zona = 'TODAS' and fecha = (select max(fecha) from m_ranking_canasta_dia)
order by posicion;
```

Las decisiones de diseño (qué es una cadena, cómo se eligió la canasta, cómo se calcula el índice) están en `docs/decisiones.md`, decisiones 11 a 15.

## Dashboard

```
python -m src.exportar          # arma data/dashboard/dashboard.duckdb (unos 3 MB) desde el modelo
streamlit run app/app.py        # lo abre en el navegador
```

El dashboard no calcula nada: muestra las métricas del modelo (ranking de la canasta, dispersión por producto, prima de marca, índice contra IPC y promociones), con un filtro de zona.
Lee `data/dashboard/dashboard.duckdb`; si no está en la PC (como en Streamlit Cloud), la baja del Release `datos-dashboard` y la renueva cada hora.
La tarea diaria lo mantiene al día: después de actualizar el modelo baja el IPC, arma esa base y la sube al Release (decisión 17).

Para publicarlo (una sola vez): en [share.streamlit.io](https://share.streamlit.io) crear una app con este repositorio, rama `main` y archivo `app/app.py`.

## Reporte semanal

```
python -m src.reporte             # la última semana completa (lunes a domingo)
python -m src.reporte --parcial   # la semana en curso, con los días que haya
python -m src.reporte --semana 2026-11-16 --sin-subir
```

Genera `reports/semanal/AAAA-MM-DD.md` (la fecha es el lunes) y lo sube al Release `reportes-semanales`. Cuenta qué cadena fue la más barata, cómo cambió el ranking y el índice frente a la semana anterior,
qué productos subieron y bajaron, las promociones y la calidad de los datos. Las consultas están en `sql/06_reporte/`.
La tarea diaria lo genera sola cuando entra el dato del domingo (o la primera vez que corre después), si la semana tiene al menos 5 días con datos (decisión 18).

## Análisis

```
python -m src.ipc               # baja el IPC del INDEC a data/externos/ipc.csv
python -m src.modelo            # actualiza el modelo
jupyter lab notebooks/01_analisis.ipynb
```

`notebooks/01_analisis.ipynb` responde las cinco preguntas con las consultas de `sql/05_analisis/`. Los criterios están en la decisión 16.
