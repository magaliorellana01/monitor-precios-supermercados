-- ¿Dónde sale más barata la canasta? Ranking de las cadenas comparables con la canasta completa, por día y zona.
--   sobre_la_mas_barata_pct: cuánto más cara es que la cadena más barata
--   ahorro_vs_mas_cara_pct:  cuánto se ahorra frente a la cadena más cara
create or replace table m_ranking_canasta_dia as
select
    fecha,
    zona,
    cadena,
    costo_canasta,
    rank() over (partition by fecha, zona order by costo_canasta)::integer as posicion,
    (count(*) over (partition by fecha, zona))::integer as n_cadenas,
    round(100.0 * (costo_canasta / min(costo_canasta) over (partition by fecha, zona) - 1), 2) as sobre_la_mas_barata_pct,
    round(100.0 * (1 - costo_canasta / max(costo_canasta) over (partition by fecha, zona)), 2) as ahorro_vs_mas_cara_pct
from m_canasta_dia
where comparable and completa
order by fecha, zona, posicion;
