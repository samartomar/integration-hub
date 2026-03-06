# SSM port forwarding to Aurora PostgreSQL via bastion
# Usage: .\run-ssm-port-forward.ps1
# Then: psql -h localhost -U clusteradmin -d integrationhub
#
# DB_HOST and BASTION_INSTANCE_ID can be overridden via env; otherwise fetched from CloudFormation.

$ErrorActionPreference = "Stop"

# Resolve bastion instance ID (from OpsAccessStack output)
$BastionInstanceId = if ($env:BASTION_INSTANCE_ID) {
    $env:BASTION_INSTANCE_ID
} else {
    $id = aws cloudformation describe-stacks --stack-name OpsAccessStack --query "Stacks[0].Outputs[?OutputKey=='BastionInstanceId'].OutputValue" --output text 2>$null
    $id = if ($id) { $id.Trim() } else { $null }
    if (-not $id -or $id -eq "None") {
        Write-Host "Error: Could not get bastion instance ID. Set BASTION_INSTANCE_ID or ensure OpsAccessStack is deployed." -ForegroundColor Red
        exit 1
    }
    $id
}

# Resolve DB host from DatabaseStack (cluster endpoint)
$DbHost = if ($env:DB_HOST) {
    $env:DB_HOST
} else {
    $endpoint = aws cloudformation describe-stacks --stack-name DatabaseStack --query "Stacks[0].Outputs[?OutputKey=='Endpoint'].OutputValue" --output text 2>$null
    if ($endpoint) { $endpoint.Trim() } else { "databasestack-clustereb0386a7-hgaeewhjqlkd.cluster-cz64udqke3sz.us-east-1.rds.amazonaws.com" }
}
$DbPort = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }
$LocalPort = if ($env:LOCAL_PORT) { $env:LOCAL_PORT } else { "5432" }
$Region = if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-1" }

# Build JSON with escaped quotes (PowerShell strips unescaped quotes when passing to aws.exe)
$params = '{\"host\":[\"' + $DbHost + '\"],\"portNumber\":[\"' + $DbPort + '\"],\"localPortNumber\":[\"' + $LocalPort + '\"]}'

Write-Host "Starting SSM port forward: localhost:${LocalPort} -> ${DbHost}:${DbPort}"
Write-Host "Connect with: psql -h localhost -p ${LocalPort} -U clusteradmin -d integrationhub"
Write-Host "Get password from Secrets Manager (DatabaseStack.SecretArn)"
Write-Host "Press Ctrl+C to stop"
Write-Host ""

$arguments = @(
    'ssm', 'start-session',
    '--target', $BastionInstanceId,
    '--document-name', 'AWS-StartPortForwardingSessionToRemoteHost',
    '--parameters', $params,
    '--region', $Region
)
aws @arguments
