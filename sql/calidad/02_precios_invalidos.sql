-- Filas con precio de lista vacío, cero o negativo (se descartan).
select count(*) filter (where motivo_descarte in ('precio_vacio', 'precio_cero_o_negativo')) as valor,
       count(*) as total,
       'vacíos: ' || (count(*) filter (where motivo_descarte = 'precio_vacio'))::varchar
         || ', cero o negativos: ' || (count(*) filter (where motivo_descarte = 'precio_cero_o_negativo'))::varchar as detalle
from precios_marcados_dia;
