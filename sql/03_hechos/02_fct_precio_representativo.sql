-- Precio representativo: la MEDIANA del precio de lista de un producto en las sucursales de una cadena, por día y zona.
-- Mediana y no promedio: un precio mal cargado o una sucursal de un barrio caro no mueven el resultado.
--
-- Cada producto sale en tres zonas: CABA, GBA y TODAS (CABA + GBA juntas). La mediana de TODAS no se puede
-- sacar de las dos anteriores, por eso se calcula aparte (grouping sets).
-- Solo productos con EAN: son los únicos comparables entre cadenas.
create table if not exists fct_precio_representativo (
    fecha date,
    cadena varchar,
    zona varchar,
    clave_producto varchar,
    n_sucursales integer,
    precio_mediana decimal(12, 2),
    precio_min decimal(12, 2),
    precio_max decimal(12, 2)
);

delete from fct_precio_representativo where fecha = date '{{FECHA}}';

insert into fct_precio_representativo
select
    p.fecha,
    c.cadena,
    coalesce(s.zona, 'TODAS') as zona,
    p.clave_producto,
    count(*)::integer as n_sucursales,
    median(p.precio_lista)::decimal(12, 2) as precio_mediana,
    min(p.precio_lista) as precio_min,
    max(p.precio_lista) as precio_max
from fct_precios p
join dim_sucursal s using (id_comercio, id_bandera, id_sucursal)
join dim_cadena c using (id_comercio, id_bandera)
where p.fecha = date '{{FECHA}}'
  and p.es_ean
group by grouping sets (
    (p.fecha, c.cadena, s.zona, p.clave_producto),
    (p.fecha, c.cadena, p.clave_producto)
);
