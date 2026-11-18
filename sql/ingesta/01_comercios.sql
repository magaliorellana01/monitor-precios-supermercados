-- Banderas del día. Entrada: vista crudo_comercio (CSV leídos como texto).
create or replace table comercios_dia as
select distinct
    id_comercio::int            as id_comercio,
    id_bandera::int             as id_bandera,
    comercio_cuit               as cuit,
    comercio_razon_social       as razon_social,
    comercio_bandera_nombre     as bandera_nombre,
    comercio_bandera_url        as bandera_url
from crudo_comercio
where regexp_full_match(id_comercio, '[0-9]+');
