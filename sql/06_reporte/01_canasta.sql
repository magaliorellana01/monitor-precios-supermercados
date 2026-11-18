-- Reporte semanal, sección 1: costo de la canasta por cadena al cierre de la semana ($hasta) y su cambio frente
-- a la fecha de comparación ($base). Zona TODAS (CABA y GBA), solo cadenas comparables con la canasta completa.
select
    a.posicion,
    a.cadena,
    a.costo_canasta::double as costo,
    a.sobre_la_mas_barata_pct,
    b.costo_canasta::double as costo_base,
    round(100.0 * (a.costo_canasta / b.costo_canasta - 1), 1) as variacion_pct,
    b.posicion as posicion_base
from m_ranking_canasta_dia a
left join m_ranking_canasta_dia b on b.cadena = a.cadena and b.zona = a.zona and b.fecha = $base
where a.zona = 'TODAS' and a.fecha = $hasta
order by a.posicion;
