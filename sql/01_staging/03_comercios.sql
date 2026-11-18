-- Banderas (marcas comerciales) informadas cada día.
create or replace temp view stg_comercios as
select
    fecha,
    id_comercio,
    id_bandera,
    cuit,
    razon_social,
    bandera_nombre,
    bandera_url
from read_parquet('{{DIR_DATOS}}/comercios/fecha=*/comercios.parquet', hive_partitioning = true);
