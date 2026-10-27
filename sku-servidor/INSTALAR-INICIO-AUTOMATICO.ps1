. (Join-Path $PSScriptRoot 'python.ps1')
$skuExe = Join-Path $PSScriptRoot 'SKU-JAD-Servidor.exe'
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'config.json'))) { throw 'Primero ejecuta INICIAR.bat una vez y guarda la clave de acceso.' }
if (Test-Path -LiteralPath $skuExe) { $skuAction = New-ScheduledTaskAction -Execute $skuExe -WorkingDirectory $PSScriptRoot }
else { $skuPython = Get-SkuPython; $skuServerPath = Join-Path $PSScriptRoot 'server.py'; $skuAction = New-ScheduledTaskAction -Execute $skuPython -Argument ('"' + $skuServerPath + '"') -WorkingDirectory $PSScriptRoot }
$skuTrigger = New-ScheduledTaskTrigger -AtStartup
$skuSettings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$skuPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName 'SKU-JAD-Servidor' -Action $skuAction -Trigger $skuTrigger -Settings $skuSettings -Principal $skuPrincipal -Force | Out-Null
Write-Host 'Inicio automático instalado. Cierra la ventana de INICIAR.bat antes de arrancar la tarea para no ocupar el mismo puerto.'
Read-Host 'Presiona Enter para cerrar'
