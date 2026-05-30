param(
    [switch]$StaticOnly,
    [string]$BackendUrl = "http://127.0.0.1:8000",
    [int]$TimeoutSeconds = 10
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-IsTextSourceFile {
    param([System.IO.FileInfo]$File)

    $textExtensions = @(
        ".css", ".html", ".js", ".jsx", ".json", ".md", ".mjs",
        ".ps1", ".py", ".toml", ".ts", ".tsx", ".yaml", ".yml"
    )
    return $textExtensions -contains $File.Extension.ToLowerInvariant()
}

function Test-IsExcludedPath {
    param([string]$Path)

    $normalized = $Path.Replace("/", "\")
    $excludedSegments = @(
        "\.git\", "\node_modules\", "\dist\", "\__pycache__\", "\.venv\", "\venv\",
        "\models_cache\", "\vector_store\", "\generated_files\", "\session_attachments\",
        "\workspace_data\", "\knowledge_base\", "\references\Proma-main\"
    )

    foreach ($segment in $excludedSegments) {
        if ($normalized.Contains($segment)) {
            return $true
        }
    }

    $leaf = Split-Path $normalized -Leaf
    return $leaf -in @("app.db", ".env")
}

function Get-ProjectSourceFiles {
    $roots = @("backend", "frontend\src", "frontend\scripts", "scripts")
    $files = @()

    foreach ($root in $roots) {
        $path = Join-Path $RepoRoot $root
        if (-not (Test-Path $path)) {
            continue
        }

        $files += Get-ChildItem -LiteralPath $path -Recurse -File |
            Where-Object { (Test-IsTextSourceFile $_) -and -not (Test-IsExcludedPath $_.FullName) }
    }

    return $files
}

function Find-PatternInFiles {
    param(
        [System.IO.FileInfo[]]$Files,
        [string]$Pattern,
        [string]$Label
    )

    $findings = @()
    foreach ($file in $Files) {
        $matches = Select-String -LiteralPath $file.FullName -Pattern $Pattern -AllMatches -ErrorAction SilentlyContinue
        foreach ($match in $matches) {
            $relative = [System.IO.Path]::GetRelativePath($RepoRoot, $file.FullName)
            $findings += [pscustomobject]@{
                Check = $Label
                File = $relative
                Line = $match.LineNumber
                Text = $match.Line.Trim()
            }
        }
    }
    return $findings
}

Write-Step "Static source checks"
$sourceFiles = Get-ProjectSourceFiles
$findings = @()
$findings += Find-PatternInFiles -Files $sourceFiles -Pattern '(?i)\b[A-Z]:[\\/]' -Label "absolute-windows-path"

$frontendPath = Join-Path $RepoRoot "frontend\src"
if (Test-Path $frontendPath) {
    $frontendFiles = Get-ChildItem -LiteralPath $frontendPath -Recurse -File |
        Where-Object { (Test-IsTextSourceFile $_) -and -not (Test-IsExcludedPath $_.FullName) }
    $findings += Find-PatternInFiles -Files $frontendFiles -Pattern 'localhost|127\.0\.0\.1' -Label "frontend-hardcoded-server"
}

$appConstants = Join-Path $RepoRoot "frontend\src\renderer\constants\app.ts"
$serverAtoms = Join-Path $RepoRoot "frontend\src\renderer\atoms\server-atoms.ts"
if (-not (Test-Path $appConstants)) {
    $findings += [pscustomobject]@{ Check = "frontend-config"; File = "frontend/src/renderer/constants/app.ts"; Line = 0; Text = "missing" }
}
if (-not (Test-Path $serverAtoms)) {
    $findings += [pscustomobject]@{ Check = "frontend-config"; File = "frontend/src/renderer/atoms/server-atoms.ts"; Line = 0; Text = "missing" }
}
if ((Test-Path $appConstants) -and -not (Select-String -LiteralPath $appConstants -Pattern 'VITE_DEFAULT_API_BASE_URL' -Quiet)) {
    $findings += [pscustomobject]@{ Check = "frontend-config"; File = "frontend/src/renderer/constants/app.ts"; Line = 0; Text = "VITE_DEFAULT_API_BASE_URL not used" }
}
if ((Test-Path $serverAtoms) -and -not (Select-String -LiteralPath $serverAtoms -Pattern 'localStorage|DEFAULT_API_BASE_URL' -Quiet)) {
    $findings += [pscustomobject]@{ Check = "frontend-config"; File = "frontend/src/renderer/atoms/server-atoms.ts"; Line = 0; Text = "server URL persistence/config missing" }
}

if ($findings.Count -gt 0) {
    $findings | Format-Table -AutoSize
    Write-Host ""
    Write-Host "Static checks failed." -ForegroundColor Red
    exit 1
}

Write-Host "Static checks passed." -ForegroundColor Green

if ($StaticOnly) {
    Write-Step "Done"
    Write-Host "Static-only Windows readiness check completed." -ForegroundColor Green
    exit 0
}

Write-Step "Backend health"
try {
    $health = Invoke-RestMethod -Method Get -Uri "$BackendUrl/health" -TimeoutSec $TimeoutSeconds
    if ($health.status -ne "ok") {
        throw "Unexpected health status: $($health.status)"
    }
    Write-Host "Backend health OK: $BackendUrl" -ForegroundColor Green
} catch {
    Write-Host "Backend is not reachable: $BackendUrl" -ForegroundColor Red
    Write-Host "Start backend first, or rerun with -StaticOnly for source checks only." -ForegroundColor Yellow
    exit 1
}

Write-Step "Done"
Write-Host "Windows readiness check completed." -ForegroundColor Green
