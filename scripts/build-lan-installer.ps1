param(
    [string]$BackendUrl = "",
    [string]$BackendHost = "",
    [int]$BackendPort = 8000,
    [string]$Version = "",
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendDir = Join-Path $RepoRoot "frontend"
$PackageJson = Join-Path $FrontendDir "package.json"

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

function Normalize-BackendUrl {
    param([string]$Url)

    $normalized = $Url.Trim().TrimEnd("/")
    if (-not $normalized) {
        throw "Backend URL is empty."
    }
    if ($normalized -notmatch "^https?://") {
        $normalized = "http://$normalized"
    }
    return $normalized
}

if (-not (Test-Path -LiteralPath $PackageJson)) {
    throw "frontend/package.json not found."
}

if (-not $BackendUrl.Trim()) {
    if (-not $BackendHost.Trim()) {
        $BackendHost = Get-PrimaryIPv4
    }
    if (-not $BackendHost) {
        throw "Could not detect LAN IP. Pass -BackendUrl or -BackendHost explicitly."
    }
    $BackendUrl = "http://$BackendHost`:$BackendPort"
}

$BackendUrl = Normalize-BackendUrl $BackendUrl

$package = Get-Content -LiteralPath $PackageJson -Raw | ConvertFrom-Json
$effectiveVersion = if ($Version.Trim()) { $Version.Trim() } else { [string]$package.version }

Write-Host "Building Project_R installer" -ForegroundColor Cyan
Write-Host "Default backend URL: $BackendUrl" -ForegroundColor Green
Write-Host "Installer version: $effectiveVersion" -ForegroundColor Green

Set-Location -LiteralPath $FrontendDir
$env:VITE_DEFAULT_API_BASE_URL = $BackendUrl

& bun run build
if ($LASTEXITCODE -ne 0) {
    throw "Frontend build failed."
}

$indexHtml = Join-Path $FrontendDir "dist\renderer\index.html"
if (-not (Test-Path -LiteralPath $indexHtml)) {
    throw "Built renderer index.html was not found: $indexHtml"
}

$indexText = Get-Content -LiteralPath $indexHtml -Raw
if ($indexText -match '(src|href)="/assets/') {
    throw "Renderer assets are absolute /assets paths. Electron file:// packaging requires relative ./assets paths."
}

$builderArgs = @("electron-builder", "--win", "nsis", "--config", "electron-builder.yml")
if ($Version.Trim()) {
    $builderArgs += "--config.extraMetadata.version=$effectiveVersion"
}

& bunx @builderArgs
if ($LASTEXITCODE -ne 0) {
    throw "Electron installer build failed."
}

$asarPath = Join-Path $FrontendDir "release\win-unpacked\resources\app.asar"
if (-not (Test-Path -LiteralPath $asarPath)) {
    throw "Built app.asar was not found: $asarPath"
}

$asarText = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($asarPath))
if (-not $asarText.Contains($BackendUrl)) {
    throw "Built app.asar does not contain expected backend URL: $BackendUrl"
}

$installer = Get-ChildItem -LiteralPath (Join-Path $FrontendDir "release") -Filter "Project_R-Setup-$effectiveVersion.exe" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($null -eq $installer) {
    throw "Installer was not found for version $effectiveVersion."
}

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $installer.FullName

if (-not $SkipSmokeTest) {
    $smokeScript = Join-Path $RepoRoot "scripts\smoke-electron-package.ps1"
    & powershell -ExecutionPolicy Bypass -File $smokeScript
    if ($LASTEXITCODE -ne 0) {
        throw "Electron package smoke test failed."
    }
}

[pscustomobject]@{
    Installer = $installer.FullName
    Version = $effectiveVersion
    BackendUrl = $BackendUrl
    SizeBytes = $installer.Length
    SHA256 = $hash.Hash
} | Format-List
