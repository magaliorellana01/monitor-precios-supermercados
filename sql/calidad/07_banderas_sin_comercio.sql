-- Banderas con precios que no figuran en comercio.csv.
with con_precios as (
    select distinct id_comercio, id_bandera from precios_dia
),
sin_comercio as (
    select * from con_precios anti join comercios_dia using (id_comercio, id_bandera)
)
select (select count(*) from sin_comercio) as valor,
       (select count(*) from con_precios) as total,
       coalesce((select string_agg(id_comercio::varchar || '-' || id_bandera::varchar, ', ') from sin_comercio), '-') as detalle;
