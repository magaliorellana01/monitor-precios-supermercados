-- Precios de sucursales que no figuran en sucursales.csv (en todo el país). No se pueden ubicar
-- en una zona, así que quedan afuera del filtro.
with sucursales as (
    select distinct id_comercio, id_bandera, id_sucursal from crudo_sucursales
),
todos as (
    select id_comercio, id_bandera, id_sucursal from crudo_productos
    where regexp_full_match(id_comercio, '[0-9]+')
),
huerfanos as (
    select * from todos anti join sucursales using (id_comercio, id_bandera, id_sucursal)
)
select (select count(*) from huerfanos) as valor,
       (select count(*) from todos) as total,
       'comercios: ' || coalesce((select string_agg(distinct id_comercio, ', ') from huerfanos), '-') as detalle;
