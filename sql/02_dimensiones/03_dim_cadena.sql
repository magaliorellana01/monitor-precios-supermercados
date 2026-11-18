-- Una fila por bandera (id_comercio + id_bandera). La "cadena" es el nombre que se usa para comparar y sale de
-- config/cadenas.csv: Changomas junta sus tres banderas y Carrefour queda separado por formato, porque los
-- precios de un Express y de un Hipermercado son distintos.
-- Una bandera que no está en el archivo de configuración queda con rubro 'sin_clasificar' y el modelo avisa.
create or replace table dim_cadena as
with ultima as (
    select
        id_comercio,
        id_bandera,
        arg_max(bandera_nombre, fecha) as bandera_nombre,
        arg_max(razon_social, fecha) as razon_social
    from stg_comercios
    group by all
)
select
    u.id_comercio,
    u.id_bandera,
    u.bandera_nombre,
    u.razon_social,
    coalesce(c.cadena, u.bandera_nombre) as cadena,
    coalesce(c.rubro, 'sin_clasificar') as rubro
from ultima u
left join stg_cfg_cadenas c
  on c.id_comercio::int = u.id_comercio
 and c.id_bandera::int = u.id_bandera
order by u.id_comercio, u.id_bandera;
