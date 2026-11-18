-- Descripción de cada producto según cada comercio, con la presentación normalizada.
--
-- Las unidades vienen escritas de muchas formas ("GR", "gr", "gr.", "grm"...). Se llevan a una unidad base:
--   g (gramos), ml (mililitros) o unidad. Lo que no se reconoce queda como 'otro'.
create or replace temp macro unidad_base(u) as
    case
        when lower(rtrim(trim(u), '.')) in ('g', 'gr', 'grm', 'grs', 'gm', 'gramo', 'gramos', 'kg', 'kgm', 'kgs', 'kilo', 'kilos') then 'g'
        when lower(rtrim(trim(u), '.')) in ('ml', 'cc', 'cm3', 'cmq', 'l', 'lt', 'lts', 'litro', 'litros') then 'ml'
        when lower(rtrim(trim(u), '.')) in ('un', 'uni', 'unid', 'unidad', 'unidades', 'ud', 'u', 'ea', 'cu', 'pck', 'pack', 'paq', 'paquete') then 'unidad'
        else 'otro'
    end;

-- Factor para llevar la cantidad a la unidad base (kg -> g, l -> ml).
create or replace temp macro factor_unidad(u) as
    case
        when lower(rtrim(trim(u), '.')) in ('kg', 'kgm', 'kgs', 'kilo', 'kilos', 'l', 'lt', 'lts', 'litro', 'litros') then 1000.0
        else 1.0
    end;

create or replace temp view stg_productos as
select
    fecha,
    id_comercio,
    id_producto,
    es_ean,
    case when es_ean then id_producto else 'c' || id_comercio::varchar || '-' || id_producto end as clave_producto,
    nullif(trim(descripcion), '') as descripcion,
    nullif(upper(trim(marca)), '') as marca,
    try_cast(replace(cantidad_presentacion, ',', '.') as double) * factor_unidad(unidad_presentacion) as contenido,
    unidad_base(unidad_presentacion) as unidad
from read_parquet('{{DIR_DATOS}}/productos/fecha=*/productos.parquet', hive_partitioning = true);
