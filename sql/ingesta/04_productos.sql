-- Descripción de cada producto según cada comercio (la descripción es texto libre de cada cadena).
-- Se toma el valor más frecuente entre las sucursales de la zona.
create or replace table productos_dia as
select
    p.id_comercio::int                                      as id_comercio,
    p.id_producto,
    p.productos_ean = '1'                                   as es_ean,
    mode(p.productos_descripcion)                           as descripcion,
    mode(p.productos_marca)                                 as marca,
    mode(p.productos_cantidad_presentacion)                 as cantidad_presentacion,
    mode(p.productos_unidad_medida_presentacion)            as unidad_presentacion,
    mode(p.productos_cantidad_referencia)                   as cantidad_referencia,
    mode(p.productos_unidad_medida_referencia)              as unidad_referencia
from crudo_productos p
join sucursales_dia s
  on s.id_comercio = p.id_comercio::int
 and s.id_bandera  = p.id_bandera::int
 and s.id_sucursal = p.id_sucursal
where regexp_full_match(p.id_comercio, '[0-9]+')
group by all
order by id_comercio, id_producto;
