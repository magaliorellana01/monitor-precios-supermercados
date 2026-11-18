-- La configuración queda guardada en el modelo, así la app y los análisis la leen sin depender de la carpeta config/.

create or replace table parametros as
select nombre, valor, descripcion from stg_cfg_parametros;

create or replace table dim_canasta as
select
    ean as clave_producto,
    categoria,
    producto
from stg_cfg_canasta;

-- Pares de marcas para la prima de marca: en cada categoría, un producto líder y uno alternativo
-- de la misma presentación.
create or replace table dim_par_marca as
select
    categoria,
    rol,
    ean as clave_producto,
    marca,
    producto
from stg_cfg_marcas;
