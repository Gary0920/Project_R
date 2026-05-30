param(
    [string]$BackendUrl = "http://127.0.0.1:8000",
    [string]$Username = "admin",
    [string]$Password = "Project_R_2026",
    [switch]$SkipDependencyCheck
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $RepoRoot "backend"
$BackendPython = Join-Path $BackendDir "venv\Scripts\python.exe"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-PythonModule {
    param([string]$ModuleName)

    & $BackendPython -c "import $ModuleName" 2>$null
    return $LASTEXITCODE -eq 0
}

function Invoke-ProjectRApi {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [string]$Token = ""
    )

    $headers = @{}
    if ($Token) {
        $headers.Authorization = "Bearer $Token"
    }

    $params = @{
        Method = $Method
        Uri = "$BackendUrl$Path"
        TimeoutSec = 600
        Headers = $headers
    }

    if ($null -ne $Body) {
        $params.ContentType = "application/json"
        $params.Body = ($Body | ConvertTo-Json -Depth 10)
    }

    Invoke-RestMethod @params
}

if (-not (Test-Path $BackendDir)) {
    throw "Backend directory not found: $BackendDir"
}

if (-not (Test-Path $BackendPython)) {
    throw "Backend venv python not found: $BackendPython"
}

Write-Step "Checking backend dependencies"
if (-not $SkipDependencyCheck) {
    $missing = @()
    foreach ($module in @("yaml", "docx", "pypdf")) {
        if (-not (Test-PythonModule -ModuleName $module)) {
            $missing += $module
        }
    }

    if ($missing.Count -gt 0) {
        Write-Host "Missing Python modules in backend venv: $($missing -join ', ')" -ForegroundColor Red
        Write-Host "Please run this once, then retry:" -ForegroundColor Yellow
        Write-Host "cd `"$BackendDir`"; .\venv\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor Yellow
        exit 1
    }
}

Write-Step "Checking backend health"
try {
    Invoke-ProjectRApi -Method Get -Path "/health" | Out-Null
} catch {
    Write-Host "Backend is not reachable: $BackendUrl" -ForegroundColor Red
    Write-Host "Start it first:" -ForegroundColor Yellow
    Write-Host "cd `"$BackendDir`"; .\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000" -ForegroundColor Yellow
    exit 1
}

Write-Step "Logging in"
$login = Invoke-ProjectRApi -Method Post -Path "/auth/login" -Body @{
    username = $Username
    password = $Password
}
$token = $login.token
if (-not $token) {
    $token = $login.access_token
}
if (-not $token) {
    throw "Login succeeded but token was not returned."
}

Write-Step "Checking GBrain health"
try {
    $gbrainStatus = Invoke-ProjectRApi -Method Get -Path "/admin/knowledge/status" -Token $token
    if ($gbrainStatus.readiness -and $gbrainStatus.readiness.errors -and $gbrainStatus.readiness.errors.Count -gt 0) {
        Write-Host "GBrain is not ready:" -ForegroundColor Yellow
        $gbrainStatus.readiness.errors | ForEach-Object { Write-Host "- $_" -ForegroundColor Yellow }
        Write-Host "Try: .\scripts\start-gbrain.ps1 -Restart" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Unable to read GBrain status from Project_R." -ForegroundColor Yellow
}

Write-Step "Refreshing GBrain company-wiki source"
$refresh = Invoke-ProjectRApi -Method Post -Path "/admin/knowledge/refresh" -Token $token
$refresh | ConvertTo-Json -Depth 10

Write-Step "GBrain knowledge status"
$status = Invoke-ProjectRApi -Method Get -Path "/admin/knowledge/status" -Token $token
$status | ConvertTo-Json -Depth 10

Write-Step "Done"
Write-Host "GBrain company-wiki refresh completed." -ForegroundColor Green
