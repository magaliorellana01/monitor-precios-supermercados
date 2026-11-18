-- Variación de filas guardadas frente al último día guardado, en %. Negativo = caída.
-- Sin día anterior no hay con qué comparar: valor null.
with hoy as (select count(*) as filas from precios_dia),
     antes as (select count(*) as filas from precios_anteriores)
select case when antes.filas = 0 then null
            else round(100.0 * (hoy.filas / antes.filas - 1), 1)
       end as valor,
       antes.filas as total,
       'hoy: ' || hoy.filas::varchar || ' filas, día anterior: ' || antes.filas::varchar as detalle
from hoy, antes;
