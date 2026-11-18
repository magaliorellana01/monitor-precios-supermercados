-- Reporte semanal, sección 3: variación del precio de cada producto de la canasta entre la fecha de comparación y el
-- cierre. Precio del producto = mediana entre cadenas de sus precios medianos; solo con al menos $min_cadenas cadenas
-- en las dos fechas (así que el producto sea el mismo y la comparación sea entre las mismas cadenas).
with comunes as (
    select a.clave_producto, a.cadena, a.producto, a.categoria, b.precio_mediana::double as precio_base, a.precio_mediana::double as precio_hasta
    from precio_canasta_dia a
    join precio_canasta_dia b on b.clave_producto = a.clave_producto and b.cadena = a.cadena and b.zona = a.zona and b.fecha = $base
    where a.zona = 'TODAS' and a.fecha = $hasta and a.precio_mediana > 0 and b.precio_mediana > 0
)
select producto, categoria,
       median(precio_base) as precio_base,
       median(precio_hasta) as precio_hasta,
       round(100 * median(precio_hasta / precio_base - 1), 1) as variacion_pct,
       count(*)::integer as n_cadenas
from comunes
group by producto, categoria
having count(*) >= $min_cadenas
order by variacion_pct desc;
