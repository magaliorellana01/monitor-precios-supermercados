-- Pregunta 3: ¿cuánto más se paga por la marca líder frente a la alternativa?
-- Mediana entre cadenas y días de la prima dentro de cada cadena. Solo si al menos 5 cadenas venden los dos.
select categoria,
       round(median(prima_pct), 1) as prima_mediana_pct,
       round(min(prima_pct), 1) as prima_min_pct,
       round(max(prima_pct), 1) as prima_max_pct,
       count(distinct cadena) as n_cadenas,
       count(distinct fecha) as dias
from m_prima_marca_dia
where zona = 'TODAS'
group by categoria
having count(distinct cadena) >= 5
order by prima_mediana_pct desc;
