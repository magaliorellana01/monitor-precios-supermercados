-- Reporte semanal, sección 5: cuántos días con datos tuvo la semana y cuántas cadenas pudieron compararse al cierre.
select
    (select count(distinct fecha) from m_canasta_dia where fecha between $desde and $hasta)::integer as dias_con_datos,
    (select count(*) from m_ranking_canasta_dia where zona = 'TODAS' and fecha = $hasta)::integer as cadenas_comparadas,
    (select count(distinct fecha) from m_canasta_dia
      where zona = 'TODAS' and comparable and not completa and fecha between $desde and $hasta)::integer as dias_con_canasta_incompleta;
