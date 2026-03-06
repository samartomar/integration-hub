# Bundle Lambda assets without Docker - uses pip --platform for Amazon Linux wheels
# Run from repo root: .\scripts\bundle-lambdas.ps1
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root

# 1. Build shared Lambda layer (common deps: psycopg2, jsonschema, PyJWT, etc.)
Write-Host "Building integrationhub-common layer..." -ForegroundColor Cyan
$layerOut = Join-Path $root ".bundled\integrationhub-common-layer"
if (Test-Path $layerOut) { Remove-Item -Recurse -Force $layerOut }
New-Item -ItemType Directory -Path (Join-Path $layerOut "python") -Force | Out-Null
$layerReq = Join-Path $root "packages\lambda-layers\integrationhub-common\requirements.txt"
$layerTarget = Join-Path $layerOut "python"
$prevErr = $ErrorActionPreference; $ErrorActionPreference = "Continue"
python -m pip install -r $layerReq -t $layerTarget --platform manylinux2014_x86_64 --python-version 3.11 --only-binary=:all: --upgrade 2>&1 | Out-Null
$err = $LASTEXITCODE; $ErrorActionPreference = $prevErr
if ($err -ne 0) {
    Write-Host "  Platform install failed, trying default..." -ForegroundColor Yellow
    $prevErr = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    python -m pip install -r $layerReq -t $layerTarget --upgrade 2>&1 | Out-Null
    $err = $LASTEXITCODE; $ErrorActionPreference = $prevErr
}
Write-Host "  -> $layerOut" -ForegroundColor Green

# 2. Sync shared modules to ai_tool
Copy-Item "apps\api\src\lambda\observability.py" "lambdas\ai_tool\" -Force
Copy-Item "apps\api\src\lambda\canonical_error.py" "lambdas\ai_tool\" -Force

$bundles = @(
    @{
        Name = "backend-lambda"
        Source = Join-Path $root "apps\api\src\lambda"
        OutDir = Join-Path $root ".bundled\backend-lambda"
    },
    @{
        Name = "ai-tool"
        Source = Join-Path $root "lambdas\ai_tool"
        OutDir = Join-Path $root ".bundled\ai-tool"
    }
)

foreach ($b in $bundles) {
    Write-Host "Bundling $($b.Name)..." -ForegroundColor Cyan
    $out = $b.OutDir
    if (Test-Path $out) { Remove-Item -Recurse -Force $out }
    New-Item -ItemType Directory -Path $out -Force | Out-Null

    # Install deps for Amazon Linux 2 (manylinux wheels)
    $reqFile = Join-Path $b.Source "requirements.txt"
    $pkgLines = Get-Content $reqFile | Where-Object { $_ -match "^\s*[a-zA-Z0-9]" -and $_ -notmatch "^\s*#" }
    $hasDeps = $pkgLines -and @($pkgLines).Count -gt 0
    if ($hasDeps) {
        $prevErr = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        python -m pip install -r $reqFile -t $out --platform manylinux2014_x86_64 --python-version 3.11 --only-binary=:all: --upgrade 2>&1 | Out-Null
        $err = $LASTEXITCODE; $ErrorActionPreference = $prevErr
        if ($err -ne 0) {
            Write-Host "  Platform install failed, trying default..." -ForegroundColor Yellow
            $prevErr = $ErrorActionPreference; $ErrorActionPreference = "Continue"
            python -m pip install -r $reqFile -t $out --upgrade 2>&1 | Out-Null
            $ErrorActionPreference = $prevErr
        }
    }

    # Copy source
    Get-ChildItem -Path $b.Source -Exclude "__pycache__","*.pyc",".bundled" | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination (Join-Path $out $_.Name) -Recurse -Force
    }
    Write-Host "  -> $out" -ForegroundColor Green
}

Write-Host "`nDone. Set USE_PREBUNDLED=1 and run: .\scripts\deploy.ps1" -ForegroundColor Yellow
