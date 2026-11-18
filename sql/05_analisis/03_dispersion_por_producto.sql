-- Pregunta 1: ¿cuánto cambia el precio del mismo producto según la cadena?
-- Mediana de los días del rango entre la cadena más cara y la más barata, solo productos de la canasta
-- y días con al menos 5 cadenas comparando (min_cadenas_dispersion).
select k.categoria, k.producto,
       round(median(d.rango_pct), 1) as rango_pct,
       round(median(d.precio_min), 0) as precio_min,
       round(median(d.precio_max), 0) as precio_max,
       max(d.n_cadenas) as n_cadenas,
       count(*) as dias
from m_dispersion_producto_dia d
join dim_canasta k using (clave_producto)
where d.zona = 'TODAS' and d.n_cadenas >= (select valor::int from parametros where nombre = 'min_cadenas_dispersion')
group by k.categoria, k.producto
order by rango_pct desc;
