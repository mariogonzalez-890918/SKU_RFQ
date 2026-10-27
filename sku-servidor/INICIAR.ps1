. (Join-Path $PSScriptRoot 'python.ps1')
Write-Host 'Direcciones de este servidor (usa la correspondiente a LAN, Radmin VPN o ZeroTier):'
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object InterfaceAlias, IPAddress | Format-Table -AutoSize
$skuExe = Join-Path $PSScriptRoot 'SKU-JAD-Servidor.exe'
if (Test-Path -LiteralPath $skuExe) { & $skuExe }
else { $skuPython = Get-SkuPython; & $skuPython (Join-Path $PSScriptRoot 'server.py') }
