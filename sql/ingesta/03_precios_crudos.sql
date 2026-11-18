-- Precios del día de las sucursales de la zona, sin limpiar. Tabla normalizada: solo ids, precios y promociones.
-- La limpieza (precios inválidos, duplicados, absurdos) está en 04_precios.sql.
create or replace table precios_crudos_dia as
select
    p.id_comercio::int                                          as id_comercio,
    p.id_bandera::int                                           as id_bandera,
    p.id_sucursal,
    p.id_producto,
    p.productos_ean = '1'                                       as es_ean,
    try_cast(p.productos_precio_lista as decimal(12, 2))        as precio_lista,
    try_cast(p.productos_precio_unitario_promo1 as decimal(12, 2)) as precio_promo1,
    nullif(trim(p.productos_leyenda_promo1), '')                as leyenda_promo1,
    try_cast(p.productos_precio_unitario_promo2 as decimal(12, 2)) as precio_promo2,
    nullif(trim(p.productos_leyenda_promo2), '')                as leyenda_promo2
from crudo_productos p
join sucursales_dia s
  on s.id_comercio = p.id_comercio::int
 and s.id_bandera  = p.id_bandera::int
 and s.id_sucursal = p.id_sucursal
where regexp_full_match(p.id_comercio, '[0-9]+');
