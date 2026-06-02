param(
    [int]$Port = 8000,
    [string]$HostAddress = "0.0.0.0",
    [switch]$Reload,
    [switch]$AddFirewallRule
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $RepoRoot "backend"
$Python = Join-Path $BackendDir "venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Backend venv not found: $Python. Create it from backend/requirements.txt before starting the LAN backend."
}

function Get-PrimaryIPv4 {
    try {
        $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
            Sort-Object RouteMetric, InterfaceMetric |
            Select-Object -First 1
        if ($null -eq $route) {
            return $null
        }
        $address = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex |
            Where-Object { $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -ne "127.0.0.1" } |
            Select-Object -First 1
        return $address.IPAddress
    } catch {
        return $null
    }
}

if ($AddFirewallRule) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Warning "Firewall rule was not added because this PowerShell window is not running as Administrator."
    } else {
        $ruleName = "Project_R Backend LAN Test ($Port)"
        $existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
        if ($null -eq $existingRule) {
            New-NetFirewallRule `
                -DisplayName $ruleName `
                -Direction Inbound `
                -Action Allow `
                -Protocol TCP `
                -LocalPort $Port `
                -Profile Private | Out-Null
            Write-Host "Added Windows Firewall rule: $ruleName" -ForegroundColor Green
        } else {
            Write-Host "Windows Firewall rule already exists: $ruleName" -ForegroundColor Yellow
        }
    }
}

$primaryIp = Get-PrimaryIPv4
if ($primaryIp) {
    Write-Host "Project_R backend will listen on $HostAddress`:$Port" -ForegroundColor Cyan
    Write-Host "LAN URL for testers: http://$primaryIp`:$Port" -ForegroundColor Green
} else {
    Write-Host "Project_R backend will listen on $HostAddress`:$Port" -ForegroundColor Cyan
    Write-Warning "Could not detect the primary LAN IP. Run ipconfig and use the IPv4 address of the active network adapter."
}

Set-Location -LiteralPath $BackendDir
$uvicornArgs = @("-m", "uvicorn", "main:app", "--host", $HostAddress, "--port", [string]$Port)
if ($Reload) {
    $uvicornArgs += "--reload"
}

& $Python @uvicornArgs
