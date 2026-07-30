# CASCADE — First-run setup (Windows PowerShell)
# Downloads the required data and model files from GitHub Releases,
# then prints the command to start the application.

$ErrorActionPreference = "Stop"

$RELEASE_BASE = "https://github.com/prawinin/CASCADE/releases/download/v1.0.0"
$REPO_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Info  { param($msg) Write-Host "[setup] $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "[setup] $msg" -ForegroundColor Yellow }

function Download-File {
    param($Url, $Dest)
    $name = Split-Path -Leaf $Dest
    if ((Test-Path $Dest) -and ((Get-Item $Dest).Length -gt 0)) {
        Write-Info "Already exists: $name — skipping."
        return
    }
    $dir = Split-Path -Parent $Dest
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    Write-Info "Downloading $name ..."
    Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
    Write-Info "Saved: $Dest"
}

# Check Docker is available
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is not installed or not on PATH. Install Docker Desktop first."
    exit 1
}

Write-Info "CASCADE setup starting..."

# Pre-create target directories before Docker runs
New-Item -ItemType Directory -Force -Path "$REPO_ROOT\data" | Out-Null
New-Item -ItemType Directory -Force -Path "$REPO_ROOT\app\models" | Out-Null

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}

if ($python -and (Test-Path "$REPO_ROOT\scripts\download_data.py")) {
    & $python.Source "$REPO_ROOT\scripts\download_data.py"
} else {
    Download-File "$RELEASE_BASE/drug_database.sqlite"  "$REPO_ROOT\data\drug_database.sqlite"
    Download-File "$RELEASE_BASE/drug_fingerprints.npz" "$REPO_ROOT\data\drug_fingerprints.npz"
    Download-File "$RELEASE_BASE/mdrepo_predictor.pt"   "$REPO_ROOT\app\models\mdrepo_predictor.pt"
}

Write-Info "All data files ready."
Write-Host ""
Write-Info "Run the app with:"
Write-Host "    python compose_up.py" -ForegroundColor Cyan
Write-Host ""
Write-Warn "Or directly with Docker Compose:"
Write-Host "    docker compose up" -ForegroundColor Cyan
Write-Host ""
