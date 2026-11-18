-- Qué cadenas se pueden comparar cada día. Es "comparable" si es un supermercado y tiene al menos
-- `min_sucursales_cadena` sucursales en esa zona (config/parametros.csv). Así una cadena con 2 sucursales
-- (La Anónima, Cooperativa Obrera en la zona) no queda como "la más cara" o "la más barata" por azar.
create or replace table m_cadena_dia as
with rubros as (
    select cadena, any_value(rubro) as rubro from dim_cadena group by cadena
)
select
    f.fecha,
    f.cadena,
    f.zona,
    r.rubro,
    f.n_sucursales,
    f.n_productos_ean,
    r.rubro = 'supermercado'
        and f.n_sucursales >= (select valor::integer from parametros where nombre = 'min_sucursales_cadena') as comparable
from fct_cobertura_dia f
join rubros r using (cadena)
order by f.fecha, f.zona, f.cadena;
