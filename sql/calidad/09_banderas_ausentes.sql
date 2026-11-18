-- Banderas que informaron el día anterior y hoy no.
with ausentes as (
    select distinct id_comercio, id_bandera from precios_anteriores
    except
    select distinct id_comercio, id_bandera from precios_dia
),
con_nombre as (
    select a.id_comercio, a.id_bandera, coalesce(c.bandera_nombre, '?') as nombre
    from ausentes a
    left join comercios_anteriores c using (id_comercio, id_bandera)
)
select (select count(*) from ausentes) as valor,
       (select count(distinct (id_comercio, id_bandera)) from precios_anteriores) as total,
       coalesce((select string_agg(id_comercio::varchar || '-' || id_bandera::varchar || ' ' || nombre, ', ')
                 from con_nombre), '-') as detalle;
