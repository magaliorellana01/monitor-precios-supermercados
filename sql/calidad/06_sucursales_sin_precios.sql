-- Sucursales de la zona que no informaron ningún precio.
with sin_precios as (
    select s.id_comercio, s.id_bandera, s.id_sucursal
    from sucursales_dia s
    anti join (select distinct id_comercio, id_bandera, id_sucursal from precios_crudos_dia) p
         using (id_comercio, id_bandera, id_sucursal)
)
select (select count(*) from sin_precios) as valor,
       (select count(*) from sucursales_dia) as total,
       'comercios: ' || coalesce((select string_agg(distinct id_comercio::varchar, ', ') from sin_precios), '-') as detalle;
