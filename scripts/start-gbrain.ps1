param(
    [switch]$Restart,
    [string]$BackendEnvPath = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $RepoRoot "backend"
$EnvPath = if ($BackendEnvPath) { $BackendEnvPath } else { Join-Path $BackendDir ".env" }

function Read-DotEnv {
    param([string]$Path)
    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }
    foreach ($line in Get-Content $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        $commentIndex = $value.IndexOf(" #")
        if ($commentIndex -ge 0) {
            $value = $value.Substring(0, $commentIndex).Trim()
        }
        $values[$key] = $value.Trim('"').Trim("'")
    }
    return $values
}

function Resolve-ProjectPath {
    param(
        [string]$Value,
        [string]$Default
    )
    $pathValue = if ($Value) { $Value } else { $Default }
    if ([System.IO.Path]::IsPathRooted($pathValue)) {
        return [System.IO.Path]::GetFullPath($pathValue)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BackendDir $pathValue))
}

function Get-FirstCsvValue {
    param([string]$Value)
    if (-not $Value) {
        return ""
    }
    foreach ($item in $Value.Split(",")) {
        $trimmed = $item.Trim()
        if ($trimmed) {
            return $trimmed
        }
    }
    return ""
}

function Get-ProcessCommandLine {
    param([int]$ProcessId)
    try {
        return (Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId").CommandLine
    } catch {
        return ""
    }
}

function Test-GBrainServeCommandLine {
    param(
        [string]$CommandLine,
        [int]$Port
    )
    if (-not $CommandLine) {
        return $false
    }
    $normalized = $CommandLine.Replace("\", "/")
    return $normalized.Contains("src/cli.ts") `
        -and $normalized.Contains("serve") `
        -and $normalized.Contains("--port") `
        -and $normalized.Contains([string]$Port)
}

function Test-ProcessAlive {
    param([int]$ProcessId)
    try {
        Get-Process -Id $ProcessId -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Clear-StalePgliteState {
    param([string]$GBrainHome)

    $brainPath = Join-Path $GBrainHome ".gbrain\brain.pglite"
    if (-not (Test-Path $brainPath)) {
        return
    }

    $lockDir = Join-Path $brainPath ".gbrain-lock"
    $lockFile = Join-Path $lockDir "lock"
    $lockPidAlive = $false
    if (Test-Path $lockFile) {
        try {
            $lock = Get-Content $lockFile -Encoding UTF8 | ConvertFrom-Json
            $lockPidAlive = Test-ProcessAlive -ProcessId ([int]$lock.pid)
        } catch {
            $lockPidAlive = $false
        }
        if (-not $lockPidAlive) {
            Remove-Item -LiteralPath $lockDir -Recurse -Force
        }
    }

    $postmasterPid = Join-Path $brainPath "postmaster.pid"
    if ((Test-Path $postmasterPid) -and -not $lockPidAlive) {
        Remove-Item -LiteralPath $postmasterPid -Force
    }
}

$envValues = Read-DotEnv -Path $EnvPath
$GBrainHome = Resolve-ProjectPath -Value $envValues["GBRAIN_HOME"] -Default ".\workspace_data\global\company-wiki"
$GBrainBaseUrl = if ($envValues["GBRAIN_BASE_URL"]) { $envValues["GBRAIN_BASE_URL"] } else { "http://127.0.0.1:3131" }
$GBrainWorkdir = Resolve-ProjectPath -Value $envValues["GBRAIN_CLI_WORKDIR"] -Default "..\reference\gbrain-master"
$Bun = if ($envValues["GBRAIN_BUN_BIN"]) { $envValues["GBRAIN_BUN_BIN"] } else { "bun" }
$Bind = if ($envValues["GBRAIN_HTTP_BIND"]) { $envValues["GBRAIN_HTTP_BIND"] } else { "127.0.0.1" }
$OllamaBaseUrl = if ($envValues["OLLAMA_BASE_URL"]) { $envValues["OLLAMA_BASE_URL"] } else { "http://127.0.0.1:11434/v1" }

$uri = [Uri]$GBrainBaseUrl
$Port = $uri.Port
if ($Port -lt 0) {
    $Port = 3131
}

if (-not (Test-Path (Join-Path $GBrainWorkdir "src\cli.ts"))) {
    throw "GBrain CLI not found: $GBrainWorkdir"
}

$existingByCommand = Get-Process -Name "bun" -ErrorAction SilentlyContinue | Where-Object {
    $cmd = Get-ProcessCommandLine -ProcessId $_.Id
    Test-GBrainServeCommandLine -CommandLine $cmd -Port $Port
}
$existingByPort = @()
try {
    $existingByPort = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            try {
                $process = Get-Process -Id $_.OwningProcess -ErrorAction Stop
                $cmd = Get-ProcessCommandLine -ProcessId $process.Id
                if ($process.ProcessName -eq "bun" -and (Test-GBrainServeCommandLine -CommandLine $cmd -Port $Port)) {
                    $process
                }
            } catch {
                $null
            }
        }
} catch {
    $existingByPort = @()
}
$existing = @($existingByCommand) + @($existingByPort) | Sort-Object -Property Id -Unique

if ($existing -and -not $Restart) {
    Write-Host "GBrain already appears to be running on port $Port." -ForegroundColor Green
    Write-Host "Health: $GBrainBaseUrl/health"
    exit 0
}

if ($existing -and $Restart) {
    foreach ($process in $existing) {
        Stop-Process -Id $process.Id -Force
    }
    Start-Sleep -Seconds 1
}

Clear-StalePgliteState -GBrainHome $GBrainHome

$env:GBRAIN_HOME = $GBrainHome
$env:OLLAMA_BASE_URL = $OllamaBaseUrl
$DeepSeekKey = if ($envValues["DEEPSEEK_API_KEY"]) {
    $envValues["DEEPSEEK_API_KEY"]
} else {
    Get-FirstCsvValue -Value $envValues["DEEPSEEK_API_KEYS"]
}
if ($DeepSeekKey) {
    $env:DEEPSEEK_API_KEY = $DeepSeekKey
}
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue

$ManifestDir = Join-Path $GBrainHome "manifests"
New-Item -ItemType Directory -Force -Path $ManifestDir | Out-Null
$LogPath = Join-Path $ManifestDir "gbrain-http-service.log"
$ErrorLogPath = Join-Path $ManifestDir "gbrain-http-service.err.log"

$args = @(
    "src/cli.ts",
    "serve",
    "--http",
    "--port",
    [string]$Port,
    "--bind",
    $Bind,
    "--suppress-bootstrap-token"
)

$process = Start-Process `
    -FilePath $Bun `
    -ArgumentList $args `
    -WorkingDirectory $GBrainWorkdir `
    -RedirectStandardOutput $LogPath `
    -RedirectStandardError $ErrorLogPath `
    -WindowStyle Hidden `
    -PassThru

$record = @{
    pid = $process.Id
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    base_url = $GBrainBaseUrl
    workdir = $GBrainWorkdir
    command = @($Bun) + $args
    log_path = $LogPath
    error_log_path = $ErrorLogPath
}
$recordPath = Join-Path $ManifestDir "gbrain-http-service.json"
$recordJson = $record | ConvertTo-Json -Depth 5
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($recordPath, $recordJson, $utf8NoBom)

Start-Sleep -Seconds 2
try {
    $health = Invoke-RestMethod -Uri "$GBrainBaseUrl/health" -TimeoutSec 5
    Write-Host "GBrain started. PID=$($process.Id), status=$($health.status)." -ForegroundColor Green
} catch {
    Write-Host "GBrain process started but health check failed. PID=$($process.Id)" -ForegroundColor Yellow
    Write-Host "Check log: $LogPath" -ForegroundColor Yellow
    Write-Host "Check error log: $ErrorLogPath" -ForegroundColor Yellow
    exit 1
}
