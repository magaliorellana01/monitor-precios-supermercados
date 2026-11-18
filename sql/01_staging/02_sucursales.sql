-- Sucursales de la zona (CABA + GBA), un registro por día.
create or replace temp view stg_sucursales as
select
    fecha,
    id_comercio,
    id_bandera,
    id_sucursal,
    nombre,
    tipo,
    calle,
    numero,
    barrio,
    codigo_postal,
    localidad,
    provincia,
    latitud,
    longitud,
    round(km_obelisco, 2) as km_obelisco,
    zona
from read_parquet('{{DIR_DATOS}}/sucursales/fecha=*/sucursales.parquet', hive_partitioning = true);
