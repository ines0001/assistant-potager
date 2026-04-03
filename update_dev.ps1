# update_dev.ps1 - Mise a jour de l'environnement de developpement
# -----------------------------------------------------------------
# Usage manuel  : .\update_dev.ps1
# Usage hook git: .\update_dev.ps1 -SkipPull
# Forcer tout   : .\update_dev.ps1 -Force
#
# Ce script :
#   1. Tire le dernier code Git (sauf si -SkipPull)
#   2. Installe les nouvelles dependances Python si requirements.txt a change
#   3. Applique les migrations SQL non encore jouees (suivi dans .migrations_applied)
#
# Prerequis :
#   - Python + pip dans le PATH
#   - psql (PostgreSQL client) dans le PATH
#   - Fichier .env.dev present (copier config.py.example et remplir les valeurs)
# -----------------------------------------------------------------

param(
    [switch]$SkipPull,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ROOT         = $PSScriptRoot
$ENV_FILE     = Join-Path $ROOT ".env.dev"
$MIGRATIONS   = Join-Path $ROOT "migrations"
$APPLIED_LOG  = Join-Path $ROOT ".migrations_applied"
$REQUIREMENTS = Join-Path $ROOT "requirements.txt"

function step($msg) { Write-Host $msg -ForegroundColor Cyan }
function ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function skip($msg) { Write-Host "  [-]  $msg" -ForegroundColor DarkGray }
function warn($msg) { Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function fail($msg) { Write-Host "  [KO] $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "=== Assistant Potager - Mise a jour env dev ===" -ForegroundColor Green
Write-Host ""

# --- Prerequis ---
if (-not (Test-Path $ENV_FILE)) {
    fail ".env.dev introuvable. Copiez config.py.example vers .env.dev et renseignez les valeurs."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    fail "python introuvable. Verifiez votre PATH."
}
if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    fail "psql introuvable. Installez le client PostgreSQL et ajoutez-le au PATH."
}

# --- Lecture de .env.dev ---
foreach ($line in Get-Content $ENV_FILE) {
    if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
    if ($line -match '^([^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
    }
}
$DB_URL = $env:DATABASE_URL
if (-not $DB_URL) { fail "DATABASE_URL absente de .env.dev." }

# --- 1. Git Pull ---
step "[1/3] Synchronisation Git..."

if ($SkipPull) {
    $before = git rev-parse ORIG_HEAD 2>$null
    $after  = git rev-parse HEAD 2>$null
    skip "pull ignore (appele depuis hook git)"
} else {
    $before = git rev-parse HEAD 2>$null
    git pull origin main
    if ($LASTEXITCODE -ne 0) { fail "git pull echoue." }
    $after = git rev-parse HEAD 2>$null
}

$changedFiles = @()
if ($before -and $after -and ($before -ne $after)) {
    $changedFiles = git diff $before $after --name-only 2>$null
}

$reqChanged = $Force -or ($changedFiles | Where-Object { $_ -eq "requirements.txt" }) -or ($before -eq $after -and -not $SkipPull)
$migChanged = $Force -or ($changedFiles | Where-Object { $_ -match "^migrations/" })

ok "HEAD : $(git rev-parse --short HEAD 2>$null)"

# --- 2. Dependances Python ---
step "[2/3] Dependances Python..."

if ($reqChanged -or $Force) {
    python -m pip install --quiet -r $REQUIREMENTS
    if ($LASTEXITCODE -ne 0) { fail "pip install echoue." }
    ok "requirements.txt installe"
} else {
    skip "requirements.txt inchange"
}

# --- 3. Migrations SQL ---
step "[3/3] Migrations SQL..."

$applied = @()
if (Test-Path $APPLIED_LOG) {
    $applied = @(Get-Content $APPLIED_LOG | Where-Object { $_ -ne "" })
}

$files     = Get-ChildItem -Path $MIGRATIONS -Filter "migration_v*.sql" | Sort-Object Name
$nbApplied = 0

foreach ($mig in $files) {
    if (-not $Force -and ($applied -contains $mig.Name)) {
        skip "$($mig.Name) (deja appliquee)"
        continue
    }

    Write-Host "  >>> $($mig.Name)..." -ForegroundColor Yellow
    $ErrorActionPreference = "Continue"
    $output = & psql $DB_URL --quiet -v ON_ERROR_STOP=1 -f $mig.FullName 2>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($exitCode -ne 0) {
        warn "$($mig.Name) - avertissement psql (souvent normal si partiellement jouee) :"
        Write-Host "      $output" -ForegroundColor DarkGray
    } else {
        ok "$($mig.Name)"
    }

    if (-not ($applied -contains $mig.Name)) {
        Add-Content -Path $APPLIED_LOG -Value $mig.Name
        $applied += $mig.Name
    }
    $nbApplied++
}

if ($nbApplied -eq 0) {
    skip "toutes les migrations sont deja appliquees"
}

Write-Host ""
Write-Host "[OK] Environnement dev a jour !" -ForegroundColor Green
Write-Host "     Lancez le bot : python bot.py" -ForegroundColor DarkGray
Write-Host ""