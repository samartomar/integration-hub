#!/usr/bin/env pwsh
# Fetch Integration Hub API URLs from CloudFormation. Updates Postman env file in-place.
# Usage: .\scripts\get-postman-urls.ps1           # print URLs
#        .\scripts\get-postman-urls.ps1 -Update  # also update postman/Integration-Hub-POC.postman_environment.json

param([switch]$Update)

$stackName = "DataPlaneStack"
$envFile = Join-Path $PSScriptRoot "..\..\postman\Integration-Hub-POC.postman_environment.json"

try {
    $outputs = aws cloudformation describe-stacks --stack-name $stackName `
        --query "Stacks[0].Outputs" --output json 2>$null | ConvertFrom-Json
    if ($outputs) {
        $vendorUrl = ($outputs | Where-Object { $_.OutputKey -eq "VendorApiInvokeUrl" }).OutputValue
        $adminUrl = ($outputs | Where-Object { $_.OutputKey -eq "AdminApiCustomDomainUrl" }).OutputValue
        if (-not $adminUrl) { $adminUrl = ($outputs | Where-Object { $_.OutputKey -eq "AdminApiInvokeUrl" }).OutputValue }
        $runtimeUrl = ($outputs | Where-Object { $_.OutputKey -eq "RuntimeApiCustomDomainUrl" }).OutputValue
        if (-not $runtimeUrl) { $runtimeUrl = ($outputs | Where-Object { $_.OutputKey -eq "RuntimeApiInvokeUrl" }).OutputValue }
        Write-Host "vendorApiUrl (REST - execute, onboarding): $vendorUrl"
        Write-Host "adminApiUrl (HTTP - admin, audit, registry): $adminUrl"
        Write-Host "runtimeApiUrl (HTTP - runtime execute, AI): $runtimeUrl"
        Write-Host ""
        if ($Update -and $vendorUrl -and $adminUrl) {
            $json = Get-Content $envFile -Raw | ConvertFrom-Json
            foreach ($v in $json.values) {
                if ($v.key -eq "baseUrlVendorApi" -or $v.key -eq "vendorApiUrl") { $v.value = $vendorUrl }
                elseif ($v.key -eq "baseUrlAdminApi" -or $v.key -eq "adminApiUrl") { $v.value = $adminUrl }
                elseif ($v.key -eq "baseUrlRuntimeApi" -and $runtimeUrl) { $v.value = $runtimeUrl }
            }
            $json | ConvertTo-Json -Depth 10 | Set-Content $envFile -NoNewline
            Write-Host "Updated $envFile with VendorApiInvokeUrl, AdminApiInvokeUrl, RuntimeApiInvokeUrl." -ForegroundColor Green
        } else {
            Write-Host "Paste into Postman, or run with -Update to auto-update env file."
        }
        Write-Host "vendorJwt, adminJwt, and runtimeJwt: use JWT (Authorization Bearer)."
    } else {
        Write-Host "Stack $stackName not found. Deploy DataPlaneStack first."
    }
} catch {
    Write-Host "Error: $_"
}
