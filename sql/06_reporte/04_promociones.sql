-- Reporte semanal, sección 4: promociones informadas en la semana, por cadena (promedio de los días de la semana).
-- Solo cadenas con al menos $min_filas precios en promoción por día en promedio.
select cadena,
       round(avg(pct_con_promo), 1) as pct_con_promo,
       round(median(descuento_mediano_pct), 1) as descuento_mediano_pct,
       count(*)::integer as dias
from m_promo_cadena_dia
where fecha between $desde and $hasta
group by cadena
having avg(filas_promo) >= $min_filas
order by pct_con_promo desc;
