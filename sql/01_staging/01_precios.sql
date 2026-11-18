-- Precios diarios ya limpios (los guarda la ingesta en data/precios/fecha=AAAA-MM-DD/). La fecha sale del nombre de la carpeta.
-- Vista temporal: no queda guardada en modelo.duckdb, así el archivo no depende de dónde están los Parquet.
--
-- clave_producto: el EAN cuando es un código estándar (comparable entre cadenas). Los códigos internos de un comercio
-- solo son únicos dentro de ese comercio, así que se les antepone el comercio para que no se mezclen.
create or replace temp view stg_precios as
select
    fecha,
    id_comercio,
    id_bandera,
    id_sucursal,
    id_producto,
    es_ean,
    case when es_ean then id_producto else 'c' || id_comercio::varchar || '-' || id_producto end as clave_producto,
    precio_lista,
    precio_promo1,
    precio_promo2
from read_parquet('{{DIR_DATOS}}/precios/fecha=*/precios.parquet', hive_partitioning = true);
