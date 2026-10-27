$ErrorActionPreference = 'Stop'
$skuConfigPath = Join-Path $PSScriptRoot 'config.json'
$skuPort = 8080
if (Test-Path -LiteralPath $skuConfigPath) { $skuPort = (Get-Content -Raw -LiteralPath $skuConfigPath | ConvertFrom-Json).port }
$skuRuleName = "SKU-JAD-TCP-$skuPort"
if (-not (Get-NetFirewallRule -Name $skuRuleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $skuRuleName -DisplayName "SKU JAD TCP $skuPort LAN y VPN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $skuPort -Profile Any | Out-Null
}
Write-Host "Puerto TCP $skuPort habilitado para las interfaces local, Radmin y ZeroTier."
Read-Host 'Presiona Enter para cerrar'
