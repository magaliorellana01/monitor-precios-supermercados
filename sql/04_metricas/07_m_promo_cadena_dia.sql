-- ¿Qué parte de los precios de cada cadena está en promoción? Por cadena y día, sobre todas las sucursales de los
-- supermercados (zona TODAS), con el precio de lista como referencia.
--   pct_con_promo:         filas con promoción general (promo1) menor al precio de lista
--   descuento_mediano_pct: cuánto baja la promoción respecto de la lista, en las filas en promoción
-- Se calcula sobre fct_precios, que conserva solo los últimos `retener_dias_fct_precios` días.
create or replace table m_promo_cadena_dia as
select
    f.fecha,
    s.cadena,
    count(*)::integer as filas,
    (count(*) filter (where f.precio_promo1 < f.precio_lista))::integer as filas_promo,
    round(100.0 * count(*) filter (where f.precio_promo1 < f.precio_lista) / count(*), 1) as pct_con_promo,
    round(100 * median(1 - f.precio_promo1 / f.precio_lista) filter (where f.precio_promo1 < f.precio_lista), 1)
        as descuento_mediano_pct
from fct_precios f
join dim_sucursal s using (id_comercio, id_bandera, id_sucursal)
where s.rubro = 'supermercado' and f.precio_lista > 0
group by f.fecha, s.cadena
order by f.fecha, s.cadena;
