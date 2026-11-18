-- Pregunta 5: ¿las promociones son reales? Por cadena, sobre el último día guardado y la ventana disponible:
--   pct_con_promo: filas con promoción general (promo1) menor al precio de lista.
--   descuento_mediano_pct: cuánto baja respecto de la lista.
--   pct_promo_permanente: de los productos que estuvieron en promo algún día, cuántos estuvieron en promo
--   todos los días en que se los observó (una promoción que nunca termina es el precio de siempre).
-- Solo cadenas con al menos 1000 filas en promo, para no concluir con 3 casos.
with ventana as (
    select max(fecha) as hasta, count(distinct fecha) as dias from fct_precios
),
base as (
    select s.cadena, f.fecha, f.id_comercio, f.id_bandera, f.id_sucursal, f.clave_producto,
           f.precio_lista, f.precio_promo1,
           (f.precio_promo1 is not null and f.precio_promo1 < f.precio_lista) as en_promo
    from fct_precios f
    join dim_sucursal s using (id_comercio, id_bandera, id_sucursal)
    where s.rubro = 'supermercado' and f.precio_lista > 0
),
por_producto as (
    select cadena, id_comercio, id_bandera, id_sucursal, clave_producto,
           count(*) as dias_observado, count(*) filter (where en_promo) as dias_en_promo
    from base
    group by all
),
permanencia as (
    select cadena,
           count(*) filter (where dias_en_promo > 0) as n_con_promo,
           round(100.0 * count(*) filter (where dias_en_promo > 0 and dias_en_promo = dias_observado and dias_observado >= 3)
                 / nullif(count(*) filter (where dias_en_promo > 0 and dias_observado >= 3), 0), 1) as pct_promo_permanente
    from por_producto
    group by cadena
),
ultimo as (
    select cadena,
           count(*) as filas,
           count(*) filter (where en_promo) as filas_promo,
           round(100.0 * count(*) filter (where en_promo) / count(*), 1) as pct_con_promo,
           round(100 * median(1 - precio_promo1 / precio_lista) filter (where en_promo), 1) as descuento_mediano_pct
    from base
    where fecha = (select hasta from ventana)
    group by cadena
)
select u.cadena, u.filas, u.filas_promo, u.pct_con_promo, u.descuento_mediano_pct, p.pct_promo_permanente
from ultimo u join permanencia p using (cadena)
where u.filas_promo >= 1000
order by u.pct_con_promo desc;
