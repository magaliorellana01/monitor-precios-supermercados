-- Una fila por sucursal, con los datos del último día en que apareció. Las sucursales que cierran se conservan,
-- porque los precios históricos siguen apuntando a ellas.
create or replace table dim_sucursal as
with ultima as (
    select
        id_comercio,
        id_bandera,
        id_sucursal,
        arg_max(nombre, fecha) as nombre,
        arg_max(tipo, fecha) as tipo,
        arg_max(calle, fecha) as calle,
        arg_max(numero, fecha) as numero,
        arg_max(barrio, fecha) as barrio,
        arg_max(localidad, fecha) as localidad,
        arg_max(provincia, fecha) as provincia,
        arg_max(latitud, fecha) as latitud,
        arg_max(longitud, fecha) as longitud,
        arg_max(km_obelisco, fecha) as km_obelisco,
        arg_max(zona, fecha) as zona,
        min(fecha) as primera_fecha,
        max(fecha) as ultima_fecha
    from stg_sucursales
    group by all
)
select
    u.*,
    c.cadena,
    c.rubro
from ultima u
left join dim_cadena c using (id_comercio, id_bandera);
