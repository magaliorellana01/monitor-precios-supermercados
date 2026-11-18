-- Reporte semanal, sección 5: advertencias y errores de los controles de calidad de los días de la semana.
-- Lee el log de la ingesta ($ruta); un control que avisa muchos días seguidos se resume en una fila.
select control, resultado, count(distinct fecha)::integer as dias, any_value(detalle) as ejemplo
from read_csv($ruta, header = true, all_varchar = true)
where fecha::date between $desde::date and $hasta::date and resultado <> 'ok'
group by control, resultado
order by resultado desc, dias desc, control;
