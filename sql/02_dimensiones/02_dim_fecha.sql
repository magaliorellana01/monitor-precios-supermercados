-- Calendario completo entre el primer y el último día con datos, para que los días sin datos se vean como huecos.
create or replace table dim_fecha as
with rango as (
    select min(fecha) as desde, max(fecha) as hasta from stg_precios
),
dias as (
    select unnest(generate_series(desde, hasta, interval 1 day))::date as fecha from rango
),
con_datos as (
    select distinct fecha from stg_precios
)
select
    d.fecha,
    isodow(d.fecha) as dia_semana,
    case isodow(d.fecha)
        when 1 then 'lunes' when 2 then 'martes' when 3 then 'miércoles' when 4 then 'jueves'
        when 5 then 'viernes' when 6 then 'sábado' else 'domingo'
    end as nombre_dia,
    date_trunc('week', d.fecha)::date as semana_inicio,
    year(d.fecha) as anio,
    month(d.fecha) as mes,
    isodow(d.fecha) >= 6 as es_fin_de_semana,
    c.fecha is not null as tiene_datos
from dias d
left join con_datos c using (fecha)
order by d.fecha;
