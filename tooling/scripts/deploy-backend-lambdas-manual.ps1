# Deploy backend Lambda code without running the full CDK pipeline.
# Run from repo root: .\scripts\deploy-backend-lambdas-manual.ps1
#
# Options:
#   -Fast               Skip layer rebuild – copy code only, zip, deploy (fastest; deps from layer)
#   -RegistryOnly       Deploy only integrationhub-registry (registry_lambda.py)
#   -VendorRegistryOnly  Deploy only integrationhub-vendor-registry (vendor_registry_lambda.py)
#   -AiGatewayOnly      Deploy only integrationhub-ai-gateway (ai_gateway_lambda.py)
#
# Next full pipeline run will sync CDK state; this is fine for temporary deploys.

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

# Backend Lambdas that share apps/api/src/lambda code (same bundle)
$BACKEND_FUNCTIONS = @(
    "integrationhub-routing",
    "integrationhub-vendor-registry",
    "integrationhub-onboarding",
    "integrationhub-audit",
    "integrationhub-registry",
    "integrationhub-endpoint-verifier",
    "integrationhub-ai-gateway"
)

Write-Host "=== Manual backend Lambda deploy ===" -ForegroundColor Cyan

$fastDeploy = $args -contains "-Fast"

# 1. Bundle (fast = code-only copy; full = layer + bundle)
$bundleDir = Join-Path $root ".bundled\backend-lambda"
if ($fastDeploy) {
    Write-Host "Fast bundle: code only (deps from layer)..." -ForegroundColor Cyan
    if (Test-Path $bundleDir) { Remove-Item -Recurse -Force $bundleDir }
    New-Item -ItemType Directory -Path $bundleDir -Force | Out-Null
    Get-ChildItem -Path "backend\lambda" -Exclude "__pycache__","*.pyc",".bundled" | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination (Join-Path $bundleDir $_.Name) -Recurse -Force
    }
} else {
    if (-not (Test-Path ".bundled\backend-lambda")) {
        Write-Host "Bundling backend-lambda (first time or .bundled missing)..." -ForegroundColor Yellow
        .\scripts\bundle-lambdas.ps1
    } else {
        Write-Host "Re-bundling backend-lambda (to pick up latest code)..." -ForegroundColor Yellow
        .\scripts\bundle-lambdas.ps1
    }
}
$zipPath = Join-Path $root "backend-lambda.zip"

# 2. Create zip (remove old zip first)
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $bundleDir "*") -DestinationPath $zipPath -CompressionLevel Fastest
Write-Host "Created $zipPath" -ForegroundColor Green

# 3. Update Lambda(s) – pass -VendorRegistryOnly, -RegistryOnly, or -AiGatewayOnly for targeted deploys
$vendorRegistryOnly = $args -contains "-VendorRegistryOnly"
$registryOnly = $args -contains "-RegistryOnly"
$aiGatewayOnly = $args -contains "-AiGatewayOnly"
$functionsToUpdate = if ($vendorRegistryOnly) {
    @("integrationhub-vendor-registry")
} elseif ($registryOnly) {
    @("integrationhub-registry")
} elseif ($aiGatewayOnly) {
    @("integrationhub-ai-gateway")
} else {
    $BACKEND_FUNCTIONS
}

foreach ($fn in $functionsToUpdate) {
    Write-Host "Updating $fn..." -ForegroundColor Cyan
    aws lambda update-function-code --function-name $fn --zip-file "fileb://$zipPath"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Failed. Function may not exist in this account/region." -ForegroundColor Red
    } else {
        Write-Host "  OK" -ForegroundColor Green
    }
}

# Cleanup
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
Write-Host "`nDone. Backend Lambdas updated." -ForegroundColor Green
Write-Host "Run full pipeline (cdk deploy) next time you have further changes." -ForegroundColor Yellow
