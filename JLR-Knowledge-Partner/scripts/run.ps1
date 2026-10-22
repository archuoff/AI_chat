# JLR Knowledge Partner - one-click setup + start (launched by "Start JLR Knowledge Partner.bat").
# First run : installs Python 3.12 / Node.js if missing, the backend and frontend packages, asks for the
#             Azure OpenAI key once, then starts everything and opens the browser.
# Later runs: only checks and starts (a few seconds).
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$venvPy = Join-Path $backend '.venv\Scripts\python.exe'

function Say($text, $color = 'Gray') { Write-Host $text -ForegroundColor $color }
function Step($text) { Write-Host ''; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) {
    Write-Host ''; Write-Host "XX  $text" -ForegroundColor Red
    Read-Host 'Press Enter to close'; exit 1
}
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Hash-File($path) { (Get-FileHash $path -Algorithm SHA256).Hash }
function Port-Open($port) {
    try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', $port); $c.Close(); return $true } catch { return $false }
}
function Winget-Install($id, $name) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "$name is not installed and winget is not available. Install $name manually, then run this again."
    }
    Say "Installing $name (this can take a few minutes)..." Yellow
    winget install -e --id $id --silent --accept-package-agreements --accept-source-agreements --scope user
    if ($LASTEXITCODE -ne 0) {
        winget install -e --id $id --silent --accept-package-agreements --accept-source-agreements
    }
    Refresh-Path
}

Clear-Host
Say '============================================================' DarkCyan
Say '   JLR Knowledge Partner  -  Tata Technologies' White
Say '============================================================' DarkCyan
Say "Folder: $root"

# ---------------------------------------------------------------- 1. Python 3.12
Step 'Python 3.12'
function Find-Python {
    foreach ($cand in @(
            { py -3.12 -c "import sys; print(sys.executable)" 2>$null },
            { python -c "import sys; print(sys.executable if sys.version_info[:2] == (3, 12) else '')" 2>$null })) {
        try { $p = (& $cand | Select-Object -First 1); if ($p -and (Test-Path $p)) { return $p } } catch {}
    }
    $default = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (Test-Path $default) { return $default }
    return $null
}
if (-not (Test-Path $venvPy)) {
    $py = Find-Python
    if (-not $py) { Winget-Install 'Python.Python.3.12' 'Python 3.12'; $py = Find-Python }
    if (-not $py) { Fail 'Python 3.12 could not be found after installing. Restart the PC and run this again.' }
    Say "Using $py"
    Step 'Creating the backend environment'
    & $py -m venv (Join-Path $backend '.venv')
    if ($LASTEXITCODE -ne 0) { Fail 'Could not create the Python environment.' }
} else { Say 'Backend environment found.' }

# ---------------------------------------------------------------- 2. backend packages
$lock = Join-Path $backend 'requirements.lock.txt'
$marker = Join-Path $backend '.venv\.installed'
$want = Hash-File $lock
if (-not (Test-Path $marker) -or (Get-Content $marker -Raw).Trim() -ne $want) {
    Step 'Installing backend packages (first time: about 5-10 minutes)'
    & $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check
    & $venvPy -m pip install -r $lock --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Say 'Exact versions failed; trying the general requirements...' Yellow
        & $venvPy -m pip install -r (Join-Path $backend 'requirements.txt') --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) { Fail 'Backend packages could not be installed. Check the internet connection and run again.' }
    }
    Set-Content $marker $want
} else { Say 'Backend packages up to date.' }

# ---------------------------------------------------------------- 3. Node.js + frontend packages
Step 'Node.js'
Refresh-Path
$nodeOk = $false
try { $v = (node --version) -replace '^v', ''; $nodeOk = ([version]$v -ge [version]'20.19.0') } catch {}
if (-not $nodeOk) { Winget-Install 'OpenJS.NodeJS.LTS' 'Node.js LTS'; try { $v = (node --version); $nodeOk = $true } catch {} }
if (-not $nodeOk) { Fail 'Node.js 20.19 or newer is needed. Restart the PC and run this again.' }
Say "Node $(node --version)"
$nmMarker = Join-Path $frontend 'node_modules\.installed'
$wantNm = Hash-File (Join-Path $frontend 'package-lock.json')
if (-not (Test-Path $nmMarker) -or (Get-Content $nmMarker -Raw).Trim() -ne $wantNm) {
    Step 'Installing frontend packages (first time: 1-3 minutes)'
    Push-Location $frontend
    npm ci --no-audit --no-fund
    $ok = $LASTEXITCODE -eq 0
    Pop-Location
    if (-not $ok) { Fail 'Frontend packages could not be installed. Check the internet connection and run again.' }
    Set-Content $nmMarker $wantNm
} else { Say 'Frontend packages up to date.' }

# ---------------------------------------------------------------- 4. settings (.env) + Azure key
Step 'Settings'
$envFile = Join-Path $backend '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $backend '.env.example') $envFile
    Say 'The assistant uses Azure OpenAI. Paste the Azure OpenAI API key for the endpoint in backend\.env' Yellow
    Say '(input is hidden; it is stored only in backend\.env on this PC).' Yellow
    $secure = Read-Host 'Azure OpenAI API key' -AsSecureString
    $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    if ($key.Trim()) {
        $text = (Get-Content $envFile -Raw) -replace '(?m)^AZURE_OPENAI_API_KEY=.*$', "AZURE_OPENAI_API_KEY=$($key.Trim())"
        [IO.File]::WriteAllText($envFile, $text, (New-Object Text.UTF8Encoding($false)))
        Say 'Key saved.' Green
    } else {
        Say 'No key entered. Edit backend\.env later (AZURE_OPENAI_API_KEY=...) - search needs it.' Yellow
    }
    $key = $null
} else { Say 'backend\.env found.' }

# ---------------------------------------------------------------- 5. accounts
Push-Location $backend
$users = & $venvPy -c "from app.auth.db import init_db, SessionLocal, User; init_db(); s = SessionLocal(); print(s.query(User).count())" 2>$null
if ("$users".Trim() -eq '0') {
    Step 'Creating the first developer account'
    & $venvPy -m app.cli create-user admin --role developer --display-name Administrator
    Say 'Write the password above down: it is shown only once.' Yellow
    Read-Host 'Press Enter to continue'
}
Pop-Location

# ---------------------------------------------------------------- 6. start
# (Start-Process joins arguments with spaces: script paths are quoted so folders with spaces work)
Step 'Starting'
if (Port-Open 8000) { Say 'Backend already running on port 8000.' }
else {
    Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $root 'start-backend.ps1') + '"') -WindowStyle Minimized
}
if (Port-Open 5173) { Say 'Frontend already running on port 5173.' }
else {
    Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $root 'start-frontend.ps1') + '"') -WindowStyle Minimized
}
Say 'Waiting for the backend (first start downloads search models, up to a few minutes)...'
$deadline = (Get-Date).AddMinutes(6)
while (-not (Port-Open 8000) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
while (-not (Port-Open 5173) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
if (-not (Port-Open 8000)) { Fail 'The backend did not start. Open the minimized "backend" window to see why.' }
Start-Sleep -Seconds 2
Start-Process 'http://localhost:5173'
Say ''
Say 'JLR Knowledge Partner is running:  http://localhost:5173' Green
Say 'Two minimized windows keep it running (backend, frontend). Close them to stop.' Gray
Start-Sleep -Seconds 6
