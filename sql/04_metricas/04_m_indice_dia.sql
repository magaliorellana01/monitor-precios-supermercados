-- Índice de precios propio, con composición fija: siempre los mismos productos (config/canasta.csv), una unidad de
-- cada uno. Vale 100 en `fecha_base_indice` (config/parametros.csv) y mide cuánto cambió el costo de esa misma canasta.
-- Que los productos no cambien es lo que hace que el índice mida solo variación de precios.
--
-- Una cadena entra en el índice si es comparable y tiene la canasta completa tanto el día base como el día medido.

create or replace table m_indice_cadena_dia as
with base as (
    select cadena, zona, costo_canasta as costo_base
    from m_canasta_dia
    where fecha = (select valor::date from parametros where nombre = 'fecha_base_indice')
      and comparable and completa
)
select
    c.fecha,
    c.cadena,
    c.zona,
    c.costo_canasta,
    b.costo_base,
    round(100.0 * c.costo_canasta / b.costo_base, 2) as indice
from m_canasta_dia c
join base b using (cadena, zona)
where c.comparable and c.completa
order by c.fecha, c.zona, c.cadena;

-- Índice general: la mediana de los índices de las cadenas de ese día. Con la mediana, que una cadena falte un día
-- (Cencosud el 12/11) mueve poco el resultado.
create or replace table m_indice_general_dia as
select
    fecha,
    zona,
    count(*)::integer as n_cadenas,
    round(median(indice), 2) as indice
from m_indice_cadena_dia
group by all
order by fecha, zona;
