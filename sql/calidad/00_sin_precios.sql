-- El día quedó sin ningún precio guardado (valor = 1 si está vacío).
select (count(*) = 0)::int as valor,
       1 as total,
       'filas guardadas: ' || count(*)::varchar as detalle
from precios_dia;
