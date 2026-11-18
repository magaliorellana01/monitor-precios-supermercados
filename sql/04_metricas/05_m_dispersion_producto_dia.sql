-- ¿Cuánto cambia el precio del mismo producto según la cadena? Por producto, zona y día, sobre los precios representativos
-- de las cadenas comparables. Solo se calcula si el producto está en al menos `min_cadenas_dispersion` cadenas
-- (config/parametros.csv): con 2 o 3 cadenas la dispersión no dice mucho.
--   rango_pct: cuánto más caro es el precio más alto que el más bajo
--   cv_pct:    coeficiente de variación (desvío / promedio), para comparar productos de precios distintos
create or replace table m_dispersion_producto_dia as
select
    r.fecha,
    r.zona,
    r.clave_producto,
    count(*)::integer as n_cadenas,
    min(r.precio_mediana) as precio_min,
    median(r.precio_mediana)::decimal(12, 2) as precio_mediana,
    max(r.precio_mediana) as precio_max,
    round(100.0 * (max(r.precio_mediana) / min(r.precio_mediana) - 1), 1) as rango_pct,
    round(100.0 * stddev_pop(r.precio_mediana) / avg(r.precio_mediana), 1) as cv_pct
from fct_precio_representativo r
join m_cadena_dia m using (fecha, cadena, zona)
where m.comparable and r.precio_mediana > 0
group by r.fecha, r.zona, r.clave_producto
having count(*) >= (select valor::integer from parametros where nombre = 'min_cadenas_dispersion')
order by r.fecha, r.zona, r.clave_producto;
