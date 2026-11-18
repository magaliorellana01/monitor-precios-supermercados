# Ejecución diaria del monitor de precios. La lanza el Programador de tareas de Windows
# (se registra una sola vez con scripts\registrar_tarea.ps1). También se puede correr a mano.
# Qué hace y por qué corre en esta PC: docs/decisiones.md, decisión 10.

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

# El Programador de tareas no siempre ve el PATH del usuario: se agrega la CLI de GitHub a mano.
$gh = "C:\Program Files\GitHub CLI"
if (Test-Path $gh) { $env:Path += ";$gh" }

$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "No se encontró $python. Crear el entorno: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
}

& $python -m src.diaria
$codigo = $LASTEXITCODE

if ($codigo -ne 0) {
    # Aviso en pantalla: sin esto una falla pasa desapercibida (en GitHub Actions llegaba un mail).
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "La descarga diaria de precios falló. Detalle en:`n$raiz\data\ingesta\ultima_ejecucion.log",
        "Monitor de precios",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
}
exit $codigo
