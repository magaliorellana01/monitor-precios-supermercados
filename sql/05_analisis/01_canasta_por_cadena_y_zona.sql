-- Pregunta 2: ¿en qué cadena sale más barata la canasta y cuánto se ahorra?
-- Último día con al menos 5 cadenas comparables con canasta completa, por zona.
with ultimo as (
    select zona, max(fecha) as fecha from m_ranking_canasta_dia group by zona
)
select r.zona, r.posicion, r.cadena, r.costo_canasta, r.sobre_la_mas_barata_pct, r.ahorro_vs_mas_cara_pct, r.n_cadenas
from m_ranking_canasta_dia r
join ultimo u using (zona, fecha)
order by r.zona, r.posicion;
