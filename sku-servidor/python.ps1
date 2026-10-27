$ErrorActionPreference = 'Stop'
function Get-SkuPython {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $resolved = & $launcher.Source -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path -LiteralPath $resolved)) { return [string]$resolved }
    }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        $resolved = & $command.Source -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path -LiteralPath $resolved)) { return [string]$resolved }
    }
    throw 'Instala Python 3.10 o posterior en el servidor y habilita Add python.exe to PATH. Luego vuelve a ejecutar INICIAR.bat.'
}
