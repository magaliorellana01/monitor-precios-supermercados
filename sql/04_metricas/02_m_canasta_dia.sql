-- Costo de la canasta por cadena, zona y día: la suma de los precios representativos (medianas) de los productos de
-- config/canasta.csv. Solo se compara entre cadenas si la canasta está completa (tiene todos los productos): si falta
-- alguno, el costo es más bajo por falta de productos y no por precio.
--
-- Faltantes temporales: a veces una cadena no informa un producto un día o dos (en los primeros 7 días, DIA dejó de informar
-- 2 productos y Vea 1). En ese caso se usa el último precio conocido de hasta `max_dias_arrastre` días atrás
-- (config/parametros.csv), como se hace en los índices de precios. Más atrás, el producto se considera faltante.
-- `n_productos_arrastrados` dice cuántos precios del día son arrastrados.
create or replace table m_canasta_dia as
with total as (
    select count(*)::integer as n from dim_canasta
),
grilla as (
    select m.fecha, m.cadena, m.zona, k.clave_producto
    from m_cadena_dia m
    cross join dim_canasta k
),
observado as (
    select fecha, cadena, zona, clave_producto, precio_mediana
    from fct_precio_representativo
    where clave_producto in (select clave_producto from dim_canasta)
),
con_precio as (
    select g.fecha, g.cadena, g.zona, g.clave_producto, o.precio_mediana, g.fecha - o.fecha as dias_de_atraso
    from grilla g
    asof left join observado o
      on g.cadena = o.cadena and g.zona = o.zona and g.clave_producto = o.clave_producto and g.fecha >= o.fecha
),
vigente as (
    select *
    from con_precio
    where precio_mediana is not null
      and dias_de_atraso <= (select valor::integer from parametros where nombre = 'max_dias_arrastre')
)
select
    v.fecha,
    v.cadena,
    v.zona,
    m.rubro,
    m.n_sucursales,
    m.comparable,
    count(*)::integer as n_productos,
    (count(*) filter (where v.dias_de_atraso > 0))::integer as n_productos_arrastrados,
    t.n as n_productos_canasta,
    count(*) = t.n as completa,
    sum(v.precio_mediana) as costo_canasta
from vigente v
cross join total t
join m_cadena_dia m using (fecha, cadena, zona)
group by v.fecha, v.cadena, v.zona, m.rubro, m.n_sucursales, m.comparable, t.n
order by v.fecha, v.zona, costo_canasta;
