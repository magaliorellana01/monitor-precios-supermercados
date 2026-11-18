-- Una fila por producto (clave_producto). Se actualiza con una ventana de los últimos 14 días: leer todo el historial
-- de descripciones en cada corrida sería cada vez más lento, y los productos que dejan de venderse se conservan.
--
--   descripcion: la más larga entre las cadenas (suele ser la más completa; DIA, por ejemplo, abrevia las marcas)
--   marca:       la más frecuente entre las cadenas
--   contenido y unidad: de las cadenas que informan el peso o el volumen (g o ml). Varias cadenas informan "1 unidad" para
--                todo, y si se tomara la más frecuente a secas esa información ganaría siempre.
create table if not exists dim_producto (
    clave_producto varchar,
    es_ean boolean,
    descripcion varchar,
    marca varchar,
    contenido double,
    unidad varchar,
    n_comercios integer,
    ultima_fecha date
);

create or replace temp table dim_producto_nuevos as
with ventana as (
    select * from stg_productos where fecha >= date '{{FECHA_MAX}}' - 14
),
unidad_elegida as (
    select clave_producto,
           coalesce(mode(unidad) filter (where unidad in ('g', 'ml')), mode(unidad)) as unidad
    from ventana
    group by clave_producto
)
select
    v.clave_producto,
    any_value(v.es_ean) as es_ean,
    arg_max(v.descripcion, length(v.descripcion)) as descripcion,
    mode(v.marca) as marca,
    mode(v.contenido) filter (where v.unidad = u.unidad) as contenido,
    any_value(u.unidad) as unidad,
    count(distinct v.id_comercio)::integer as n_comercios,
    max(v.fecha) as ultima_fecha
from ventana v
join unidad_elegida u using (clave_producto)
group by v.clave_producto;

delete from dim_producto where clave_producto in (select clave_producto from dim_producto_nuevos);
insert into dim_producto select * from dim_producto_nuevos;
