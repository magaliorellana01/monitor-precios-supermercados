-- Cuántas sucursales y productos informó cada cadena en cada día y zona. Sirve para exigir un mínimo de
-- sucursales antes de comparar cadenas, y para ver los días en que una cadena no informó.
create table if not exists fct_cobertura_dia (
    fecha date,
    cadena varchar,
    zona varchar,
    n_sucursales integer,
    n_productos_ean integer,
    n_precios integer
);

delete from fct_cobertura_dia where fecha = date '{{FECHA}}';

insert into fct_cobertura_dia
select
    p.fecha,
    c.cadena,
    coalesce(s.zona, 'TODAS') as zona,
    count(distinct p.id_comercio::varchar || '-' || p.id_bandera::varchar || '-' || p.id_sucursal)::integer as n_sucursales,
    (count(distinct p.clave_producto) filter (where p.es_ean))::integer as n_productos_ean,
    count(*)::integer as n_precios
from fct_precios p
join dim_sucursal s using (id_comercio, id_bandera, id_sucursal)
join dim_cadena c using (id_comercio, id_bandera)
where p.fecha = date '{{FECHA}}'
group by grouping sets (
    (p.fecha, c.cadena, s.zona),
    (p.fecha, c.cadena)
);
