-- Una fila por sucursal, producto y día. Este archivo y los demás de 03_hechos se ejecutan UNA VEZ POR CADA DÍA NUEVO
-- ({{FECHA}}), no con todo el historial: el modelo es incremental. Si un día se reprocesa, se borra y se vuelve a cargar.
--
-- Se guardan solo los últimos `retener_dias_fct_precios` días (config/parametros.csv): cada día ocupa ~43 MB en DuckDB y
-- el detalle por sucursal de hace meses no se usa. La historia de largo plazo está en fct_precio_representativo
-- y los Parquet completos siguen en data/precios/ y en los Releases.
create table if not exists fct_precios (
    fecha date,
    id_comercio integer,
    id_bandera integer,
    id_sucursal varchar,
    clave_producto varchar,
    es_ean boolean,
    precio_lista decimal(12, 2),
    precio_promo1 decimal(12, 2),
    precio_promo2 decimal(12, 2)
);

delete from fct_precios where fecha = date '{{FECHA}}';

-- Ordenado por producto: comprime un 30% mejor que en el orden del archivo.
insert into fct_precios
select fecha, id_comercio, id_bandera, id_sucursal, clave_producto, es_ean,
       precio_lista, precio_promo1, precio_promo2
from stg_precios
where fecha = date '{{FECHA}}'
order by clave_producto, id_comercio, id_bandera, id_sucursal;

delete from fct_precios
where fecha < (select max(fecha) from fct_precios)
                - (select valor::integer from parametros where nombre = 'retener_dias_fct_precios');
