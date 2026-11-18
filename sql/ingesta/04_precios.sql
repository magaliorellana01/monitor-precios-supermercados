-- Limpieza de precios: marca cada fila con el motivo por el que se descarta (o null si se guarda).
-- Los umbrales están documentados en docs/decisiones.md (decisión 8).
--   precio_vacio            precio de lista vacío o no numérico
--   precio_cero_o_negativo  precio de lista <= 0
--   duplicado               misma sucursal y producto repetidos: se guarda la fila de menor precio válido
--   precio_absurdo          más de 100 veces o menos de 1/100 de la mediana del producto ese día
--
-- La mediana se calcula por EAN entre todas las cadenas. Para los códigos internos (es_ean = false),
-- que solo son únicos dentro de un comercio, se calcula por comercio y código.

create or replace table precios_marcados_dia as
with con_clave as (
    select *,
        case when es_ean then id_producto else id_comercio::varchar || '-' || id_producto end as clave_producto,
        row_number() over (
            partition by id_comercio, id_bandera, id_sucursal, id_producto
            order by (coalesce(precio_lista, 0) <= 0), precio_lista
        ) as orden
    from precios_crudos_dia
),
medianas as (
    select clave_producto, median(precio_lista) as mediana_producto
    from con_clave
    where precio_lista > 0
    group by 1
)
select c.*, m.mediana_producto,
    case
        when c.precio_lista is null                       then 'precio_vacio'
        when c.precio_lista <= 0                          then 'precio_cero_o_negativo'
        when c.orden > 1                                  then 'duplicado'
        when c.precio_lista > 100 * m.mediana_producto
          or c.precio_lista < m.mediana_producto / 100    then 'precio_absurdo'
    end as motivo_descarte
from con_clave c
left join medianas m using (clave_producto);

create or replace table precios_dia as
select id_comercio, id_bandera, id_sucursal, id_producto, es_ean,
       precio_lista, precio_promo1, leyenda_promo1, precio_promo2, leyenda_promo2
from precios_marcados_dia
where motivo_descarte is null
order by id_comercio, id_bandera, id_sucursal, id_producto;
