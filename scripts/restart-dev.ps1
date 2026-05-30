param(
    [int]$BackendPort = 8000,
    [int[]]$FrontendPorts = @(5173, 5174, 5175),
    [switch]$NoFrontend,
    [switch]$NoBackend
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$BackendPython = Join-Path $BackendDir "venv\Scripts\python.exe"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Stop-ProcessSafe {
    param(
        [int]$ProcessId,
        [string]$Reason
    )

    if ($ProcessId -eq 0 -or $ProcessId -eq $PID) {
        return
    }

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return
    }

    Write-Host "Stopping PID $ProcessId ($($process.ProcessName)) - $Reason" -ForegroundColor Yellow
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-ListenersOnPort {
    param([int]$Port)

    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        Stop-ProcessSafe -ProcessId $listener.OwningProcess -Reason "listening on port $Port"
    }
}

function Stop-ProjectDevProcesses {
    $repoPattern = [regex]::Escape($RepoRoot.Path)
    $backendPattern = [regex]::Escape($BackendDir)
    $frontendPattern = [regex]::Escape($FrontendDir)

    $processes = Get-CimInstance Win32_Process | Where-Object {
        $commandLine = $_.CommandLine
        if (-not $commandLine) {
            return $false
        }

        $isProjectBackend = $commandLine -match $backendPattern -and (
            $commandLine -match "uvicorn" -or
            $commandLine -match "main:app"
        )

        $isProjectFrontend = $commandLine -match $frontendPattern -and (
            $commandLine -match "scripts/dev\.mjs" -or
            $commandLine -match "vite" -or
            $commandLine -match "electron"
        )

        $isLegacyBackendLaunch = $commandLine -match $repoPattern -and
            $commandLine -match "backend" -and
            $commandLine -match "uvicorn" -and
            $commandLine -match "main:app"

        return $isProjectBackend -or $isProjectFrontend -or $isLegacyBackendLaunch
    }

    foreach ($process in $processes) {
        Stop-ProcessSafe -ProcessId $process.ProcessId -Reason "Project_R dev process"
    }
}

function Wait-PortFree {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if (-not $listener) {
            return
        }
        Start-Sleep -Milliseconds 300
    }

    throw "Port $Port is still occupied after cleanup."
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 3 | Out-Null
            return
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    throw "Service did not become ready: $Url"
}

Write-Step "Project_R dev restart"
Write-Host "Repo: $RepoRoot"

if (-not (Test-Path $BackendDir)) {
    throw "Backend directory not found: $BackendDir"
}

if (-not (Test-Path $FrontendDir)) {
    throw "Frontend directory not found: $FrontendDir"
}

if (-not (Test-Path $BackendPython)) {
    throw "Backend venv python not found: $BackendPython"
}

Write-Step "Stopping stale Project_R dev processes"
Stop-ProjectDevProcesses

Write-Step "Clearing ports"
Stop-ListenersOnPort -Port $BackendPort
foreach ($port in $FrontendPorts) {
    Stop-ListenersOnPort -Port $port
}
Wait-PortFree -Port $BackendPort

if (-not $NoBackend) {
    Write-Step "Starting backend on port $BackendPort"
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command",
        "cd `"$BackendDir`"; .\venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port $BackendPort"
    ) -WorkingDirectory $BackendDir

    Wait-HttpOk -Url "http://127.0.0.1:$BackendPort/health"
    Write-Host "Backend ready: http://127.0.0.1:$BackendPort" -ForegroundColor Green
}

if (-not $NoFrontend) {
    Write-Step "Starting frontend"
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command",
        "cd `"$FrontendDir`"; npm run dev"
    ) -WorkingDirectory $FrontendDir

    Write-Host "Frontend starting. Electron window should open shortly." -ForegroundColor Green
}

Write-Step "Done"
Write-Host "Backend URL for frontend settings: http://127.0.0.1:$BackendPort" -ForegroundColor Green
