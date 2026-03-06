# integrationhub-common Lambda Layer

Shared Python dependencies for Integration Hub Lambda functions. Reduces deployment size and build time by packaging heavy third-party libs once.

## Dependencies

| Package | Used by |
|---------|---------|
| aws-xray-sdk | Backend Lambdas |
| jsonschema | Backend + AI Tool |
| psycopg2-binary | Backend + AI Tool |
| PyJWT | Backend Lambdas |
| requests | Backend Lambdas |

Excluded: boto3, botocore (provided by Lambda runtime).

## Build

From repo root:

```bash
./layers/integrationhub-common/build.sh
```

Output: `.bundled/integrationhub-common-layer/python/`

## Update Dependencies

1. Edit `layers/integrationhub-common/requirements.txt`
2. Rebuild: `./layers/integrationhub-common/build.sh`
3. Deploy: pipeline or `cdk deploy`
