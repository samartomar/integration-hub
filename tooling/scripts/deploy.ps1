# Full deployment script for Integration Hub
# Prerequisites: AWS CLI configured, Node/npx for CDK
# Option A: Docker running -> uses Docker for Lambda bundling
# Option B: No Docker -> run .\scripts\bundle-lambdas.ps1 first, then USE_PREBUNDLED=1

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

# Check for pre-bundled assets (no Docker path)
$usePrebundled = $env:USE_PREBUNDLED -match "^(1|true|yes)$"
if ($usePrebundled) {
    if (-not (Test-Path ".bundled\backend-lambda")) {
        Write-Host "Running bundle script first (USE_PREBUNDLED=1 but .bundled missing)..." -ForegroundColor Yellow
        .\tooling\scripts\bundle-lambdas.ps1
    }
    $env:USE_PREBUNDLED = "1"
}

# Sync shared modules to ai_tool for CDK bundling (buildspec does this in CI)
Copy-Item "apps\api\src\lambda\observability.py" "lambdas\ai_tool\" -Force
Copy-Item "apps\api\src\lambda\canonical_error.py" "lambdas\ai_tool\" -Force

# Deploy in dependency order; skip PipelineStack if GitHub config not ready
$stacks = "FoundationStack", "DatabaseStack", "OpsAccessStack", "DataPlaneStack"
Write-Host "Deploying: $($stacks -join ', ')" -ForegroundColor Cyan
Write-Host ""

npx aws-cdk deploy $stacks --require-approval never --output cdk-out-2

# If you hit export errors (FoundationStack/DatabaseStack), try:
# 1. cdk bootstrap aws://ACCOUNT/REGION
# 2. Deploy stacks one at a time: FoundationStack -> DatabaseStack -> ... -> DataPlaneStack
# 3. Or use Docker: unset USE_PREBUNDLED and ensure Docker Desktop is running
