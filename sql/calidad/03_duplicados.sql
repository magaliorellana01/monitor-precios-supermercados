-- Filas repetidas para la misma sucursal y producto (se guarda una sola).
with repetidas as (
    select * from precios_marcados_dia where motivo_descarte = 'duplicado'
)
select (select count(*) from repetidas) as valor,
       (select count(*) from precios_marcados_dia) as total,
       'comercios: ' || coalesce((select string_agg(distinct id_comercio::varchar, ', ') from repetidas), '-') as detalle;
