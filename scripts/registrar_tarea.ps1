# Registra en el Programador de tareas de Windows la ejecución diaria del monitor de precios.
# Se corre UNA sola vez, desde PowerShell, sin permisos de administrador:
#
#     .\scripts\registrar_tarea.ps1                  # todos los días a las 15:00
#     .\scripts\registrar_tarea.ps1 -Hora "16:30"    # otra hora
#
# Para sacarla:  Unregister-ScheduledTask -TaskName "Monitor precios supermercados" -Confirm:$false

param([string]$Hora = "15:00")

$nombre = "Monitor precios supermercados"
$raiz = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "tarea_diaria.ps1"

$accion = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $raiz `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""

$disparador = New-ScheduledTaskTrigger -Daily -At $Hora

# StartWhenAvailable: si la PC estaba apagada a la hora indicada, corre apenas se prende.
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)

# Corre con tu sesión abierta (no pide contraseña); si no hay sesión, espera a que la abras.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparador `
    -Settings $config -Principal $principal -Force | Out-Null

Write-Host "Tarea '$nombre' registrada: todos los días a las $Hora."
Write-Host "Para probarla ahora:  Start-ScheduledTask -TaskName '$nombre'"
