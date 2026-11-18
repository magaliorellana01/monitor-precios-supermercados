-- Archivos de configuración (carpeta config/). Se leen como texto y se tipan en las dimensiones.
create or replace temp view stg_cfg_cadenas as
select * from read_csv('{{DIR_CONFIG}}/cadenas.csv', header = true, all_varchar = true);

create or replace temp view stg_cfg_canasta as
select * from read_csv('{{DIR_CONFIG}}/canasta.csv', header = true, all_varchar = true);

create or replace temp view stg_cfg_marcas as
select * from read_csv('{{DIR_CONFIG}}/marcas.csv', header = true, all_varchar = true);

create or replace temp view stg_cfg_parametros as
select * from read_csv('{{DIR_CONFIG}}/parametros.csv', header = true, all_varchar = true);
