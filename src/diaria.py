"""Ejecución diaria completa, pensada para correr sola desde el Programador de tareas de Windows.

    python -m src.diaria

Hace, en orden:
    1. Baja de los Releases lo que falte en data/ (útil si se cambió de PC o se borró la carpeta).
    2. Corre la ingesta: descarga los días nuevos, los controla y los guarda.
    3. Sube a los Releases los días nuevos y los logs.
    4. Actualiza el modelo (data/modelo.duckdb) con los días nuevos.
    5. Baja el IPC, arma la base chica del dashboard y la sube al Release `datos-dashboard`.

Si la ingesta falla, igual sube lo que haya salido bien y los logs (con el motivo del error), y termina con
código de salida 1. Todo lo que se imprime queda también en data/ingesta/ultima_ejecucion.log.

Por qué corre en esta PC y no en GitHub Actions: docs/decisiones.md, decisión 10.
"""

from __future__ import annotations

import logging
import sys

from . import almacen, exportar, ingesta, ipc, modelo

DIAS_A_BAJAR = 10

log = logging.getLogger("diaria")


def main() -> int:
    archivo = ingesta.DIR_DATOS / "ingesta" / "ultima_ejecucion.log"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(archivo, mode="w", encoding="utf-8")],
        force=True,
    )

    codigo = 0

    # Si falla (sin internet, sin sesión de gh) no se corta: lo que ya está en data/ alcanza para seguir.
    try:
        almacen.bajar(DIAS_A_BAJAR)
    except (almacen.ErrorGh, OSError) as e:
        log.warning("No se pudo bajar lo guardado en los Releases, se sigue con lo que hay en data/: %s", e)

    if ingesta.main([]) != 0:
        codigo = 1

    # Se sube igual aunque la ingesta haya fallado: los logs tienen el motivo y puede haber días buenos.
    try:
        almacen.subir()
    except (almacen.ErrorGh, OSError) as e:
        log.error("No se pudo subir a los Releases (¿`gh auth login`?): %s", e)
        codigo = 1

    # El modelo va al final: tarda más y no es crítico. Los datos ya quedaron guardados y subidos.
    try:
        if modelo.ejecutar() != 0:
            codigo = 1
    except Exception as e:  # noqa: BLE001 - cualquier falla del modelo se informa pero no pierde datos
        log.error("No se pudo actualizar el modelo: %s", e)
        codigo = 1

    # El dashboard es lo último y lo menos crítico: si el IPC no baja, se usa el último que haya.
    try:
        if ipc.main() != 0:
            log.warning("No se pudo bajar el IPC: el dashboard usa el último que haya guardado")
        exportar.exportar()
        almacen.subir_dashboard()
    except Exception as e:  # noqa: BLE001 - se informa, pero los datos ya están guardados
        log.error("No se pudo actualizar el dashboard: %s", e)
        codigo = 1

    log.info("Ejecución diaria terminada con código %d", codigo)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
