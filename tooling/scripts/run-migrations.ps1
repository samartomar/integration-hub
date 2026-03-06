# Run Alembic migrations against Aurora PostgreSQL
# Options:
#   1. With SSM tunnel: Start .\run-ssm-port-forward.ps1 in another terminal first
#   2. Or set DATABASE_URL directly (e.g. from local dev DB)
#
# Usage: .\scripts\run-migrations.ps1
# Env:   DB_SECRET_ARN or DATABASE_URL (optional - script fetches from CloudFormation if unset)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# Resolve DB connection
if (-not $env:DATABASE_URL) {
    if ($env:DB_SECRET_ARN) {
        Write-Host "Using DB_SECRET_ARN from environment"
    } else {
        Write-Host "Fetching secret ARN from DatabaseStack..."
        $secretArn = aws cloudformation describe-stacks --stack-name DatabaseStack --query "Stacks[0].Outputs[?OutputKey=='SecretArn'].OutputValue" --output text 2>$null
        $secretArn = if ($secretArn) { $secretArn.Trim() } else { $null }
        if ($secretArn -and $secretArn -ne "None") {
            $env:DB_SECRET_ARN = $secretArn
            Write-Host "  Using SecretArn from DatabaseStack"
        }
    }

    if (-not $env:DB_SECRET_ARN) {
        Write-Host "Error: Set DATABASE_URL or DB_SECRET_ARN, or deploy DatabaseStack (exports secret-arn)" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "Running migrations..." -ForegroundColor Cyan
python tooling/scripts/run_migrations.py
$code = $LASTEXITCODE
Write-Host ""
if ($code -eq 0) {
    Write-Host "Migrations completed successfully." -ForegroundColor Green
} else {
    Write-Host "Migrations failed (exit $code)." -ForegroundColor Red
    Write-Host "Ensure SSM port-forward is running: .\scripts\run-ssm-port-forward.ps1" -ForegroundColor Yellow
}
exit $code
