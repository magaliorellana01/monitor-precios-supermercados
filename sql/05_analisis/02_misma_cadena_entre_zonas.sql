-- Pregunta 1 (por zona): ¿la misma cadena cobra distinto en CABA y en GBA?
-- Se compara el costo de la canasta de cada cadena en las dos zonas, el mismo día.
with ultimo as (select max(fecha) as fecha from m_ranking_canasta_dia)
select c.cadena,
       c.costo_canasta as costo_caba,
       g.costo_canasta as costo_gba,
       round(100.0 * (g.costo_canasta / c.costo_canasta - 1), 1) as gba_vs_caba_pct
from m_ranking_canasta_dia c
join m_ranking_canasta_dia g on g.fecha = c.fecha and g.cadena = c.cadena and g.zona = 'GBA'
join ultimo u on u.fecha = c.fecha
where c.zona = 'CABA'
order by gba_vs_caba_pct desc;
