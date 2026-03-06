# Clean Windows task runner for local development.
# Design:
# - local-* targets are DB-only + local API + local UIs (no Docker dependency).
# - docker-* targets are explicit and isolated.

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet(
        "local-up", "local-up-aws", "local-down", "local-db-init", "local-sync-db", "local-seed-db", "local-logs", "local-health",
        "docker-up", "docker-down", "docker-logs",
        "install-ui", "dev-ui", "dev-ui-aws", "dev-admin", "dev-partners", "build-ui"
    )]
    [string]$Target
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$LocalStateDir = Join-Path $RepoRoot ".local"
$LocalApiPidFile = Join-Path $LocalStateDir "hub-api.pid"
$LocalApiLogFile = Join-Path $LocalStateDir "hub-api.log"
$LocalApiErrLogFile = Join-Path $LocalStateDir "hub-api.err.log"

function Set-DbEnv {
    $env:PGHOST = "localhost"
    $env:PGPORT = "5434"
    $env:PGUSER = "hub"
    $env:PGPASSWORD = "hub"
    $env:PGDATABASE = "hub"
    $env:DATABASE_URL = "postgresql://hub:hub@localhost:5434/hub"
    $env:DB_URL = "postgresql://hub:hub@localhost:5434/hub"
}

function Set-ApiEnv {
    Set-DbEnv
    $env:RUN_ENV = "local"
    $env:USE_BEDROCK = "false"
    $env:ADMIN_IDP_ISSUER = "https://integrator-8163795.okta.com/oauth2/default/"
    $env:VENDOR_IDP_ISSUER = "https://integrator-8163795.okta.com/oauth2/aus10oqaqhv1yjZqy698/"
    $env:RUNTIME_IDP_ISSUER = "https://integrator-8163795.okta.com/oauth2/aus10oq9izh5L8rJB698/"
    $env:IDP_ISSUER = $env:RUNTIME_IDP_ISSUER
    $env:IDP_AUDIENCE = "api://hub-runtime"
    $env:RUNTIME_API_AUDIENCE = "api://hub-runtime"
    $env:ADMIN_API_AUDIENCE = "api://default"
    $env:VENDOR_API_AUDIENCE = "api://hub-vendor"
    $env:EXECUTE_SCOPE = ""
    $env:AI_EXECUTE_SCOPE = ""
    $env:AI_GATEWAY_API_KEY = "local-dev"
    $env:AI_GATEWAY_SOURCE_VENDOR = "LH001"
    $env:RUNTIME_API_URL = "http://localhost:8080"
    $env:ADMIN_REQUIRED_GROUP = "admin"
    $env:PHI_APPROVED_GROUP = "admin-phi"
    $env:AUTH_BYPASS = "false"
}

function Test-ApiHealthy {
    try {
        if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
            $null = & curl.exe -sS -m 2 "http://localhost:8080/health" 2>$null
        } else {
            $null = Invoke-RestMethod -Uri "http://localhost:8080/health" -Method Get -TimeoutSec 2
        }
        return $LASTEXITCODE -eq 0 -or $?
    } catch {
        return $false
    }
}

function Stop-ProcessOnPort([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($conn) {
            $conn | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
        }
    } catch {}
}

function Start-LocalApi {
    if (Test-ApiHealthy) {
        Write-Host "Local API already healthy on :8080." -ForegroundColor Green
        return
    }
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "python is not available in PATH; cannot start local API."
    }
    if (-not (Test-Path $LocalStateDir)) {
        New-Item -ItemType Directory -Path $LocalStateDir -Force | Out-Null
    }
    Remove-Item $LocalApiPidFile, $LocalApiLogFile, $LocalApiErrLogFile -Force -ErrorAction SilentlyContinue
    Stop-ProcessOnPort 8080

    $cmd = @(
        "`$env:PGHOST='localhost'"
        "`$env:PGPORT='5434'"
        "`$env:PGUSER='hub'"
        "`$env:PGPASSWORD='hub'"
        "`$env:PGDATABASE='hub'"
        "`$env:DATABASE_URL='postgresql://hub:hub@localhost:5434/hub'"
        "`$env:DB_URL='postgresql://hub:hub@localhost:5434/hub'"
        "`$env:RUN_ENV='local'"
        "`$env:USE_BEDROCK='false'"
        "`$env:ADMIN_IDP_ISSUER='https://integrator-8163795.okta.com/oauth2/default/'"
        "`$env:VENDOR_IDP_ISSUER='https://integrator-8163795.okta.com/oauth2/aus10oqaqhv1yjZqy698/'"
        "`$env:RUNTIME_IDP_ISSUER='https://integrator-8163795.okta.com/oauth2/aus10oq9izh5L8rJB698/'"
        "`$env:IDP_ISSUER='https://integrator-8163795.okta.com/oauth2/aus10oq9izh5L8rJB698/'"
        "`$env:IDP_AUDIENCE='api://hub-runtime'"
        "`$env:RUNTIME_API_AUDIENCE='api://hub-runtime'"
        "`$env:ADMIN_API_AUDIENCE='api://default'"
        "`$env:VENDOR_API_AUDIENCE='api://hub-vendor'"
        "`$env:EXECUTE_SCOPE=''"
        "`$env:AI_EXECUTE_SCOPE=''"
        "`$env:AI_GATEWAY_API_KEY='local-dev'"
        "`$env:AI_GATEWAY_SOURCE_VENDOR='LH001'"
        "`$env:RUNTIME_API_URL='http://localhost:8080'"
        "`$env:ADMIN_REQUIRED_GROUP='admin'"
        "`$env:PHI_APPROVED_GROUP='admin-phi'"
        "`$env:AUTH_BYPASS='false'"
        "cd '$RepoRoot'"
        "python -m uvicorn apps.api.local.app:app --host 0.0.0.0 --port 8080"
    ) -join "; "

    Write-Host "Starting local API..." -ForegroundColor Cyan
    $proc = Start-Process powershell `
        -ArgumentList "-NoProfile", "-Command", $cmd `
        -WindowStyle Hidden `
        -RedirectStandardOutput $LocalApiLogFile `
        -RedirectStandardError $LocalApiErrLogFile `
        -PassThru
    Set-Content -Path $LocalApiPidFile -Value $proc.Id -Encoding ascii

    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-ApiHealthy) {
            Write-Host "Local API is healthy on :8080." -ForegroundColor Green
            return
        }
    }
    throw "Local API did not become healthy. Check $LocalApiErrLogFile"
}

function Stop-LocalApi {
    if (Test-Path $LocalApiPidFile) {
        try {
            $pidValue = Get-Content $LocalApiPidFile -ErrorAction SilentlyContinue
            if ($pidValue) { Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue }
        } catch {}
        Remove-Item $LocalApiPidFile -Force -ErrorAction SilentlyContinue
    }
    Stop-ProcessOnPort 8080
}

function Invoke-LocalDbInit {
    Write-Host "Running migrations + seed..." -ForegroundColor Cyan
    Set-DbEnv
    Push-Location $RepoRoot
    try { python tooling/scripts/local_db_init.py } finally { Pop-Location }
    Write-Host "DB init complete." -ForegroundColor Green
}

function Invoke-LocalSyncDb {
    Write-Host "Running migrations only..." -ForegroundColor Cyan
    Set-DbEnv
    Push-Location $RepoRoot
    try { python tooling/scripts/local_db_init.py --migrate-only } finally { Pop-Location }
    Write-Host "DB migrations complete." -ForegroundColor Green
}

function Invoke-LocalSeedDb {
    Write-Host "Running seed only..." -ForegroundColor Cyan
    Set-DbEnv
    Push-Location $RepoRoot
    try { python tooling/scripts/local_db_init.py --seed-only } finally { Pop-Location }
    Write-Host "DB seed complete." -ForegroundColor Green
}

function Invoke-InstallUi {
    Write-Host "Installing UI dependencies..." -ForegroundColor Cyan
    Push-Location $RepoRoot
    try { npm install } finally { Pop-Location }
    Write-Host "UI install complete." -ForegroundColor Green
}

function Start-UiPortals {
    if (-not (Test-Path (Join-Path $RepoRoot "apps\web-cip\node_modules"))) {
        Invoke-InstallUi
    }
    $adminPath = Join-Path $RepoRoot "apps\web-cip"
    $partnersPath = Join-Path $RepoRoot "apps\web-partners"
    Start-Process cmd -ArgumentList "/c", "cd /d `"$adminPath`" && npm run dev" -WindowStyle Hidden
    Start-Process cmd -ArgumentList "/c", "cd /d `"$partnersPath`" && npm run dev" -WindowStyle Hidden
}

function Invoke-LocalUp {
    Write-Host "Starting local stack (DB-only + local API + UIs)..." -ForegroundColor Cyan
    Invoke-LocalSyncDb
    Start-LocalApi
    Start-UiPortals
    Write-Host "Done. API: http://localhost:8080 | Admin: http://localhost:5173 | Vendor: http://localhost:5174" -ForegroundColor Green
}

function Invoke-LocalUpAws {
    Write-Host "Starting local UIs with AWS API settings..." -ForegroundColor Cyan
    Invoke-DevUiAws
}

function Invoke-LocalDown {
    Write-Host "Stopping local stack..." -ForegroundColor Cyan
    Stop-ProcessOnPort 5173
    Stop-ProcessOnPort 5174
    Stop-LocalApi
    Write-Host "Done." -ForegroundColor Green
}

function Invoke-LocalLogs {
    if (Test-Path $LocalApiLogFile) {
        Write-Host "Tailing local API logs..." -ForegroundColor Cyan
        Get-Content $LocalApiLogFile -Wait
    } else {
        Write-Host "No local API log found at $LocalApiLogFile" -ForegroundColor Yellow
    }
}

function Invoke-LocalHealth {
    Write-Host "API health:" -ForegroundColor Cyan
    try {
        if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
            & curl.exe -sS -m 3 "http://localhost:8080/health"
            return
        }
        $r = Invoke-RestMethod -Uri "http://localhost:8080/health" -Method Get -TimeoutSec 3
        $r | ConvertTo-Json
    } catch {
        Write-Host "Not reachable: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Invoke-DockerUp {
    Write-Host "Starting docker services explicitly..." -ForegroundColor Cyan
    docker compose up -d --build
}

function Invoke-DockerDown {
    Write-Host "Stopping docker services explicitly..." -ForegroundColor Cyan
    docker compose down -v
}

function Invoke-DockerLogs {
    docker compose logs -f
}

function Invoke-DevAdmin {
    Push-Location (Join-Path $RepoRoot "apps\web-cip")
    try { npm run dev } finally { Pop-Location }
}

function Invoke-DevPartners {
    Push-Location (Join-Path $RepoRoot "apps\web-partners")
    try { npm run dev } finally { Pop-Location }
}

function Invoke-BuildUi {
    Push-Location (Join-Path $RepoRoot "apps\web-cip")
    try { npm run build } finally { Pop-Location }
    Push-Location (Join-Path $RepoRoot "apps\web-partners")
    try { npm run build } finally { Pop-Location }
    Write-Host "UI build complete." -ForegroundColor Green
}

function Get-AwsEnvVars {
    $vars = @{}
    Push-Location $RepoRoot
    try {
        $out = python tooling/scripts/load_env_config.py --vite 2>$null
        foreach ($line in ($out -split "`n")) {
            if ($line -match '^export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
                $vars[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
            }
        }
    } finally { Pop-Location }
    $envAwsPath = Join-Path $RepoRoot ".env.aws"
    if (Test-Path $envAwsPath) {
        Get-Content $envAwsPath | ForEach-Object {
            if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$' -and $_ -notmatch '^\s*#') {
                $vars[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
            }
        }
    }
    return $vars
}

function New-EnvBlock([hashtable]$baseVars, [string]$appTag) {
    $vars = @{}
    foreach ($k in $baseVars.Keys) { $vars[$k] = $baseVars[$k] }

    $oktaKeys = @(
        "VITE_OKTA_ISSUER",
        "VITE_OKTA_CLIENT_ID",
        "VITE_OKTA_AUDIENCE",
        "VITE_OKTA_SCOPES",
        "VITE_OKTA_CONNECTION",
        "VITE_OKTA_REDIRECT_URI",
        "VITE_OKTA_REDIRECT_PATH"
    )
    foreach ($baseKey in $oktaKeys) {
        $appKey = "${baseKey}_$appTag"
        if ($vars.ContainsKey($appKey) -and $vars[$appKey]) {
            $vars[$baseKey] = $vars[$appKey]
        }
    }

    $envParts = @()
    foreach ($k in $vars.Keys) {
        $v = ($vars[$k] -replace "'", "''")
        $envParts += "`$env:$k='$v'"
    }
    return ($envParts -join "; ")
}

function Invoke-DevUiAws {
    if (-not (Test-Path (Join-Path $RepoRoot "apps\web-cip\node_modules"))) { Invoke-InstallUi }
    $awsEnv = Get-AwsEnvVars
    $adminEnvBlock = New-EnvBlock -baseVars $awsEnv -appTag "ADMIN"
    $vendorEnvBlock = New-EnvBlock -baseVars $awsEnv -appTag "VENDOR"
    $adminPath = Join-Path $RepoRoot "apps\web-cip"
    $partnersPath = Join-Path $RepoRoot "apps\web-partners"
    $adminCmd = if ($adminEnvBlock) { "$adminEnvBlock; cd '$adminPath'; npm run dev" } else { "cd '$adminPath'; npm run dev" }
    $partnersCmd = if ($vendorEnvBlock) { "$vendorEnvBlock; cd '$partnersPath'; npm run dev" } else { "cd '$partnersPath'; npm run dev" }
    Start-Process powershell -ArgumentList "-Command", $adminCmd -WindowStyle Hidden
    Start-Process powershell -ArgumentList "-Command", $partnersCmd -WindowStyle Hidden
    Write-Host "Admin: http://localhost:5173 | Vendor: http://localhost:5174" -ForegroundColor Green
}

switch ($Target) {
    "local-up"       { Invoke-LocalUp }
    "local-up-aws"   { Invoke-LocalUpAws }
    "local-down"     { Invoke-LocalDown }
    "local-db-init"  { Invoke-LocalDbInit }
    "local-sync-db"  { Invoke-LocalSyncDb }
    "local-seed-db"  { Invoke-LocalSeedDb }
    "local-logs"     { Invoke-LocalLogs }
    "local-health"   { Invoke-LocalHealth }
    "docker-up"      { Invoke-DockerUp }
    "docker-down"    { Invoke-DockerDown }
    "docker-logs"    { Invoke-DockerLogs }
    "install-ui"     { Invoke-InstallUi }
    "dev-ui"         { Invoke-DevUiAws }
    "dev-ui-aws"     { Invoke-DevUiAws }
    "dev-admin"      { Invoke-DevAdmin }
    "dev-partners"   { Invoke-DevPartners }
    "build-ui"       { Invoke-BuildUi }
}
