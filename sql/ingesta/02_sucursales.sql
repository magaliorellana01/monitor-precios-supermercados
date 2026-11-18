-- Sucursales de CABA + GBA (ver docs/decisiones.md, decisión 3).
--   CABA: provincia AR-C, aunque la coordenada esté mal cargada.
--   GBA:  el resto de las sucursales a 40 km o menos del Obelisco (-34.6037, -58.3816).
create or replace table sucursales_dia as
with base as (
    select
        id_comercio::int                                  as id_comercio,
        id_bandera::int                                   as id_bandera,
        id_sucursal,
        sucursales_nombre                                 as nombre,
        lower(sucursales_tipo)                            as tipo,
        sucursales_calle                                  as calle,
        sucursales_numero                                 as numero,
        sucursales_barrio                                 as barrio,
        sucursales_codigo_postal                          as codigo_postal,
        sucursales_localidad                              as localidad,
        sucursales_provincia                              as provincia,
        try_cast(sucursales_latitud as double)            as latitud,
        try_cast(sucursales_longitud as double)           as longitud
    from crudo_sucursales
    where regexp_full_match(id_comercio, '[0-9]+')
),
con_distancia as (
    select *,
        2 * 6371 * asin(sqrt(
            pow(sin(radians(latitud - (-34.6037)) / 2), 2) +
            cos(radians(-34.6037)) * cos(radians(latitud)) *
            pow(sin(radians(longitud - (-58.3816)) / 2), 2)
        )) as km_obelisco
    from base
)
select *,
    case
        when provincia = 'AR-C' then 'CABA'
        when km_obelisco <= 40 then 'GBA'
    end as zona
from con_distancia
where provincia = 'AR-C' or km_obelisco <= 40;
