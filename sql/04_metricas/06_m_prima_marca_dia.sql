-- Prima de marca: cuánto más caro es el producto líder que su alternativa de la misma presentación, DENTRO DE LA MISMA
-- cadena y día (así se compara en la misma góndola y no se mezcla con "cadena cara"). Los pares están en config/marcas.csv.
--   prima_pct = precio líder / precio alternativa - 1
-- Solo hay prima si la cadena vende los dos productos ese día.
create or replace table m_prima_marca_dia as
with precios as (
    select
        r.fecha,
        r.cadena,
        r.zona,
        m.categoria,
        m.rol,
        r.precio_mediana
    from fct_precio_representativo r
    join dim_par_marca m using (clave_producto)
    join m_cadena_dia c using (fecha, cadena, zona)
    where c.comparable
),
pares as (
    select
        fecha,
        cadena,
        zona,
        categoria,
        median(precio_mediana) filter (where rol = 'lider') as precio_lider,
        median(precio_mediana) filter (where rol = 'alternativa') as precio_alternativa
    from precios
    group by all
)
select
    fecha,
    cadena,
    zona,
    categoria,
    precio_lider::decimal(12, 2) as precio_lider,
    precio_alternativa::decimal(12, 2) as precio_alternativa,
    round(100.0 * (precio_lider / precio_alternativa - 1), 1) as prima_pct
from pares
where precio_lider is not null and precio_alternativa is not null
order by fecha, zona, categoria, cadena;
