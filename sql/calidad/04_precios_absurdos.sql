-- Precios más de 100 veces por encima o por debajo de la mediana del producto ese día (se descartan).
with absurdos as (
    select * from precios_marcados_dia where motivo_descarte = 'precio_absurdo'
)
select (select count(*) from absurdos) as valor,
       (select count(*) from precios_marcados_dia) as total,
       coalesce((
           select 'mayor desvío: producto ' || id_producto || ' en el comercio ' || id_comercio::varchar
                  || ' a ' || precio_lista::varchar || ' (mediana ' || round(mediana_producto, 2)::varchar || ')'
           from absurdos
           order by greatest(precio_lista / mediana_producto, mediana_producto / precio_lista) desc
           limit 1
       ), '-') as detalle;
