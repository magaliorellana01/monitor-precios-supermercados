-- Reporte semanal, sección 2: índice de precios de la canasta (base 100) al cierre y en la fecha de comparación.
select
    max(indice) filter (where fecha = $hasta) as indice_hasta,
    max(indice) filter (where fecha = $base) as indice_base,
    round(100.0 * (max(indice) filter (where fecha = $hasta) / max(indice) filter (where fecha = $base) - 1), 2) as variacion_pct
from m_indice_general_dia
where zona = 'TODAS';
