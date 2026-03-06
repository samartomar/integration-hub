#!/bin/bash
# SSM port forwarding to Aurora PostgreSQL via bastion
# Usage: ./run-ssm-port-forward.sh
# Then: psql -h localhost -U clusteradmin -d integrationhub

set -e

# Resolve bastion from OpsAccessStack output (no stale fallback)
if [ -z "$BASTION_INSTANCE_ID" ]; then
  BASTION_INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name OpsAccessStack --query "Stacks[0].Outputs[?OutputKey=='BastionInstanceId'].OutputValue" --output text 2>/dev/null | tr -d '[:space:]')
  if [ -z "$BASTION_INSTANCE_ID" ] || [ "$BASTION_INSTANCE_ID" = "None" ]; then
    echo "Error: Could not get bastion instance ID. Set BASTION_INSTANCE_ID or ensure OpsAccessStack is deployed."
    exit 1
  fi
fi
if [ -z "$DB_HOST" ]; then
  DB_HOST=$(aws cloudformation describe-stacks --stack-name DatabaseStack --query "Stacks[0].Outputs[?OutputKey=='Endpoint'].OutputValue" --output text 2>/dev/null | tr -d '[:space:]')
  DB_HOST="${DB_HOST:-databasestack-clustereb0386a7-hgaeewhjqlkd.cluster-cz64udqke3sz.us-east-1.rds.amazonaws.com}"
fi
DB_PORT="${DB_PORT:-5432}"
LOCAL_PORT="${LOCAL_PORT:-5432}"
REGION="${AWS_REGION:-us-east-1}"

echo "Starting SSM port forward: localhost:${LOCAL_PORT} -> ${DB_HOST}:${DB_PORT}"
echo "Connect with: psql -h localhost -p ${LOCAL_PORT} -U clusteradmin -d integrationhub"
echo "Get password from Secrets Manager (DatabaseStack.SecretArn)"
echo "Press Ctrl+C to stop"
echo ""

aws ssm start-session \
  --target "${BASTION_INSTANCE_ID}" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{
    \"host\":[\"${DB_HOST}\"],
    \"portNumber\":[\"${DB_PORT}\"],
    \"localPortNumber\":[\"${LOCAL_PORT}\"]
  }" \
  --region "${REGION}"
