# Delete all Integration Hub CloudFormation stacks (for fresh deploy validation)
# Order: DataPlaneStack, PipelineStack, ProdPipelineStack,
#        DatabaseStack, OpsAccessStack, FoundationStack
# Note: DatabaseStack (Aurora) can take 10+ minutes to delete

$ErrorActionPreference = "Stop"
$stacks = @(
    "DataPlaneStack",
    "PipelineStack",
    "ProdPipelineStack",
    "DatabaseStack",
    "OpsAccessStack",
    "FoundationStack"
)

Write-Host "Deleting stacks in reverse dependency order..." -ForegroundColor Cyan
foreach ($s in $stacks) {
    $exists = aws cloudformation describe-stacks --stack-name $s 2>$null
    if ($LASTEXITCODE -eq 0) {
        $status = (aws cloudformation describe-stacks --stack-name $s --query "Stacks[0].StackStatus" --output text 2>$null)
        if ($status -match "DELETE") {
            Write-Host "  $s - $status (waiting...)" -ForegroundColor Yellow
        } else {
            Write-Host "  Deleting $s..." -ForegroundColor White
            aws cloudformation delete-stack --stack-name $s
        }
    }
}

Write-Host ""
Write-Host "Waiting for deletions (DatabaseStack/Aurora may take 10+ min)..." -ForegroundColor Cyan
foreach ($s in $stacks) {
    aws cloudformation describe-stacks --stack-name $s 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        aws cloudformation wait stack-delete-complete --stack-name $s
        Write-Host "  $s deleted" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "All application stacks deleted. CDKToolkit (bootstrap) retained." -ForegroundColor Green
Write-Host "To delete bootstrap too: aws cloudformation delete-stack --stack-name CDKToolkit" -ForegroundColor Yellow
