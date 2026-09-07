param([switch]$Launch, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot

function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Fallo ejecutando $Executable (codigo $LASTEXITCODE)." }
}
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Find-Python {
    foreach ($candidate in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", 'python', 'python3')) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            & $candidate -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    return $null
}
try {
    $python = Find-Python
    $nodeReady = $false
    if (Get-Command node -ErrorAction SilentlyContinue) {
        & node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 22 ? 0 : 1)"
        $nodeReady = $LASTEXITCODE -eq 0
    }
    $venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $chromePaths = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")
    $chromeReady = @($chromePaths | Where-Object { Test-Path -LiteralPath $_ }).Count -gt 0
    $stamp = Join-Path $projectRoot '.venv\utel-setup.json'
    $signature = (Get-FileHash backend/requirements.txt).Hash + (Get-FileHash package-lock.json).Hash
    $ready = $false
    if ((Test-Path $stamp) -and (Test-Path $venvPython) -and $nodeReady -and $chromeReady -and (Test-Path 'node_modules/electron/dist/electron.exe')) {
        $previous = Get-Content $stamp -Raw | ConvertFrom-Json
        if ($previous.signature -eq $signature -and $previous.computer -eq $env:COMPUTERNAME -and $previous.root -eq $projectRoot) {
            & $venvPython -c "import fastapi, uvicorn, pydantic_settings, httpx, cloudscraper, openpyxl, docx, multipart, pypdf, phonenumbers; from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); ok=Path(p.chromium.executable_path).exists(); p.stop(); raise SystemExit(0 if ok else 1)" 2>$null
            $ready = $LASTEXITCODE -eq 0
        }
    }
    if (-not $ready) {
        Write-Host 'UTEL QA necesita preparar/verificar las dependencias de este equipo.'
        Write-Host 'Instalara Python 3.12 y Node.js LTS si faltan, librerias en .venv, Electron, Chromium y Google Chrome si falta.'
        Write-Host 'Se requiere internet y espacio en disco. Windows puede solicitar permisos de administrador.'
        if ($CheckOnly) { Write-Host 'Diagnostico: preparacion pendiente. No se instalo nada.'; exit 2 }
        $answer = Read-Host 'Autoriza la descarga e instalacion? Escriba SI para continuar'
        if ($answer.Trim() -ine 'SI') { Write-Host 'Instalacion cancelada.'; exit 1 }
        if (-not $python -or -not $nodeReady -or -not $chromeReady) {
            if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Instale App Installer de Microsoft (winget), o Python 3.12, Node.js LTS y Chrome manualmente, y vuelva a abrir Iniciar.cmd.' }
            foreach ($item in @(@(-not $python, 'Python.Python.3.12'), @(-not $nodeReady, 'OpenJS.NodeJS.LTS'), @(-not $chromeReady, 'Google.Chrome'))) {
                if ($item[0]) { Invoke-Checked 'winget' @('install', '--id', $item[1], '--exact', '--source', 'winget', '--accept-source-agreements', '--accept-package-agreements', '--disable-interactivity') }
            }
            Refresh-Path
            $python = Find-Python
        }
        if (-not $python) { throw 'Python no esta disponible. Cierre y vuelva a abrir Iniciar.cmd.' }
        if (-not (Test-Path $venvPython)) { Invoke-Checked $python @('-m', 'venv', '.venv') }
        Invoke-Checked $venvPython @('-m', 'pip', 'install', '-r', 'backend/requirements.txt')
        Invoke-Checked 'npm.cmd' @('ci')
        Invoke-Checked $venvPython @('-m', 'playwright', 'install', 'chromium')
        Invoke-Checked $venvPython @('-m', 'pip', 'check')
        if (-not (Test-Path '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env'; Write-Host 'Se creo .env: configure sus credenciales de CRM/IA antes de ejecutar automatizaciones.' }
        @{ signature = $signature; computer = $env:COMPUTERNAME; root = $projectRoot } | ConvertTo-Json | Set-Content -LiteralPath $stamp -Encoding UTF8
    }
    Write-Host 'Dependencias locales preparadas. CRM e IA requieren credenciales propias; Ollama local es opcional y se configura por separado.'
    if ($Launch) { Invoke-Checked 'node' @('scripts/launch-web.js') }
} catch { Write-Host "No se pudo preparar UTEL QA: $_" -ForegroundColor Red; exit 1 }
