-- Columnas de la especificación SEPA que no vinieron en los CSV (indica un cambio de formato en la fuente).
with esperadas(tabla, columna) as (
    values
    ('comercio', 'id_comercio'), ('comercio', 'id_bandera'), ('comercio', 'comercio_bandera_nombre'),
    ('sucursales', 'id_comercio'), ('sucursales', 'id_bandera'), ('sucursales', 'id_sucursal'),
    ('sucursales', 'sucursales_provincia'), ('sucursales', 'sucursales_latitud'), ('sucursales', 'sucursales_longitud'),
    ('productos', 'id_comercio'), ('productos', 'id_bandera'), ('productos', 'id_sucursal'),
    ('productos', 'id_producto'), ('productos', 'productos_ean'), ('productos', 'productos_descripcion'),
    ('productos', 'productos_precio_lista'), ('productos', 'productos_precio_unitario_promo1'),
    ('productos', 'productos_precio_unitario_promo2')
),
presentes as (
    select 'comercio' as tabla, column_name as columna from (describe crudo_comercio)
    union all select 'sucursales', column_name from (describe crudo_sucursales)
    union all select 'productos', column_name from (describe crudo_productos)
),
faltantes as (
    select tabla || '.' || columna as faltante
    from esperadas anti join presentes using (tabla, columna)
)
select count(*) as valor,
       (select count(*) from esperadas) as total,
       coalesce(string_agg(faltante, ', '), '-') as detalle
from faltantes;
