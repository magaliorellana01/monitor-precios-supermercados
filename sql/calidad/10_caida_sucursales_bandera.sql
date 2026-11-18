-- Banderas presentes hoy que informaron menos de la mitad de las sucursales del día anterior.
with antes as (
    select id_comercio, id_bandera, count(distinct id_sucursal) as sucursales
    from precios_anteriores group by all
),
hoy as (
    select id_comercio, id_bandera, count(distinct id_sucursal) as sucursales
    from precios_dia group by all
),
caidas as (
    select h.id_comercio, h.id_bandera, a.sucursales as antes, h.sucursales as hoy
    from hoy h join antes a using (id_comercio, id_bandera)
    where h.sucursales < a.sucursales / 2
)
select (select count(*) from caidas) as valor,
       (select count(*) from hoy) as total,
       coalesce((select string_agg(id_comercio::varchar || '-' || id_bandera::varchar
                                   || ' (' || antes::varchar || ' -> ' || hoy::varchar || ')', ', ')
                 from caidas), '-') as detalle;
