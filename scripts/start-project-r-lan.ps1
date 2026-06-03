# start-project-r-lan.ps1
# Start Project_R backend on LAN (0.0.0.0) and frontend locally.
# Usage: .\start-project-r-lan.ps1 [-Port 8000] [-Reload] [-FirewallRule] [-NoFrontend]
param(
    [int]$Port = 8000,
    [switch]$Reload,
    [switch]$FirewallRule,
    [switch]$NoFrontend
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$Python = Join-Path $BackendDir "venv\Scripts\python.exe"

if (-not (Test-Path $Python)) { throw "Backend venv not found: $Python. Run requirements.txt first." }

function Get-PrimaryIPv4 {
    try {
        $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object RouteMetric, InterfaceMetric | Select-Object -First 1
        if ($null -eq $route) { return $null }
        $addr = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex |
            Where-Object { $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -ne "127.0.0.1" } |
            Select-Object -First 1
        return $addr.IPAddress
    } catch { return $null }
}

$primaryIp = Get-PrimaryIPv4
Write-Host "Project_R LAN launcher" -ForegroundColor Cyan
Write-Host "Backend will listen on 0.0.0.0:$Port" -ForegroundColor Cyan
if ($primaryIp) {
    Write-Host "LAN URL for testers: http://${primaryIp}:$Port" -ForegroundColor Green
} else {
    Write-Warning "Could not detect primary LAN IP. Run ipconfig to find the IPv4 address."
}

if ($FirewallRule) {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = [Security.Principal.WindowsPrincipal]::new($identity)
        $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if (-not $isAdmin) {
            Write-Warning "Firewall rule was not added (not running as Administrator)."
        } else {
            $ruleName = "Project_R Backend LAN Test ($Port)"
            if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
                New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private | Out-Null
                Write-Host "Added Windows Firewall rule: $ruleName" -ForegroundColor Green
            }
        }
    } catch {
        Write-Warning "Firewall rule check failed: $_"
    }
}

# Kill stale listeners on our port
$stale = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($s in $stale) {
    if ($s.OwningProcess -ne 0 -and $s.OwningProcess -ne $PID) {
        Stop-Process -Id $s.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

# Start backend
Write-Host "Starting backend..." -ForegroundColor Cyan
$uvicornArgs = @("-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", [string]$Port)
if ($Reload) { $uvicornArgs += "--reload" }

$backendJob = Start-Process powershell.exe -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass", "-Command",
    "cd `"$BackendDir`"; `$env:PROJECT_R_LAUNCHER='1'; & `"$Python`" $uvicornArgs"
) -WorkingDirectory $BackendDir -WindowStyle Minimized -PassThru

Write-Host "Backend starting (PID $($backendJob.Id))..." -ForegroundColor Yellow

# Wait for backend health
$deadline = (Get-Date).AddSeconds(60)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -Method Get -TimeoutSec 3 | Out-Null
        $ready = $true
        break
    } catch { Start-Sleep -Milliseconds 500 }
}

if (-not $ready) { throw "Backend did not become ready on 127.0.0.1:$Port" }
Write-Host "Backend ready: http://127.0.0.1:$Port" -ForegroundColor Green
if ($primaryIp) {
    Write-Host "Backend also reachable at: http://${primaryIp}:$Port" -ForegroundColor Green
}

# Start frontend
if (-not $NoFrontend) {
    Write-Host "Starting frontend..." -ForegroundColor Cyan
    $bun = Get-Command bun.exe -ErrorAction SilentlyContinue
    if (-not $bun) { $bun = Get-Command bun -ErrorAction SilentlyContinue }
    if (-not $bun) { throw "Bun was not found in PATH." }
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) { throw "node_modules not found. Run bun install in frontend first." }

    Start-Process powershell.exe -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-Command",
        "cd `"$FrontendDir`"; `$env:PROJECT_R_LAUNCHER='1'; `$env:PROJECT_R_FRONTEND_PORT='5174'; `$env:PROJECT_R_STRICT_FRONTEND_PORT='1'; & `"$($bun.Source)`" run dev"
    ) -WorkingDirectory $FrontendDir -WindowStyle Minimized

    Write-Host "Frontend starting. Electron window should open shortly." -ForegroundColor Green
}

Write-Host "Done." -ForegroundColor Cyan
if ($primaryIp) {
    Write-Host ""
    Write-Host "Share this URL with LAN testers: http://${primaryIp}:$Port" -ForegroundColor Green
} else {
    Write-Host "Check ipconfig for your LAN IP and share: http://YOUR-IP:$Port" -ForegroundColor Yellow
}
