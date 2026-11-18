-- Pregunta 4: evolución del índice propio de la canasta (base 100 el día base), para comparar con el IPC.
select fecha, zona, n_cadenas, indice
from m_indice_general_dia
where zona = 'TODAS'
order by fecha;
