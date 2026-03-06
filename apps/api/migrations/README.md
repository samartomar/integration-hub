# Alembic Migrations for Aurora PostgreSQL

Migrations create and manage schemas and tables in Aurora PostgreSQL. Connection uses the `DATABASE_URL` environment variable.

## Folder Structure

```
apps/api/migrations/
├── env.py              # Uses DATABASE_URL for connection
├── script.py.mako      # Revision template
├── README.md
└── versions/
    ├── v_baseline_current_schema.py   # Baseline: full current schema (squash of v1-v45)
    └── archive/                       # Historical migrations v1-v45 (not used)
```

## Reset to Baseline

Alembic was reset to a single baseline migration matching the current database schema.

**Fresh database:** Run `alembic -c apps/api/alembic.ini upgrade head` (from repo root), or `python tooling/scripts/run_migrations.py` — applies the baseline.

**Existing database** (already at v45): Run `alembic -c apps/api/alembic.ini stamp baseline` — marks the schema as applied without running migrations.

## Tables

| Schema        | Table                          |
|---------------|--------------------------------|
| control_plane | vendors                        |
| control_plane | operations                     |
| control_plane | auth_profiles                  |
| control_plane | vendor_auth_profiles           |
| control_plane | operation_contracts            |
| control_plane | vendor_operation_allowlist     |
| control_plane | vendor_supported_operations    |
| control_plane | vendor_operation_contracts     |
| control_plane | vendor_operation_mappings      |
| control_plane | vendor_endpoints               |
| control_plane | vendor_flow_layouts            |
| data_plane    | idempotency_claims             |
| data_plane    | transactions (partitioned)     |
| data_plane    | audit_events (partitioned)     |
| data_plane    | transaction_metrics_daily      |
| data_plane    | vendor_export_jobs             |

## Running Migrations from Laptop via SSM Tunnel

Aurora has no public internet access. Use SSM port-forward through the bastion to run migrations from your laptop.

### Step 1: Install dependencies

```bash
pip install alembic psycopg2-binary
# or with dev extras:
pip install -e ".[dev]"
```

### Step 2: Start SSM port-forward

In one terminal, run the port-forward script to tunnel `localhost:5432` to Aurora:

**PowerShell (Windows):**
```powershell
.\tooling\scripts\run-ssm-port-forward.ps1
```

**Bash (Linux/macOS):**
```bash
./tooling/scripts/run-ssm-port-forward.sh
```

Leave this terminal running. It forwards `localhost:5432` → Aurora.

### Step 3: Get database credentials

Fetch the password from AWS Secrets Manager (SecretArn from DatabaseStack output):

```bash
aws secretsmanager get-secret-value --secret-id <DatabaseStack-SecretArn> --query SecretString --output text | jq -r '.password'
```

Or use the full connection string from the secret:

```bash
# Build DATABASE_URL from secret fields:
# postgresql://{username}:{password}@localhost:5432/{dbname}
```

### Step 4: Set DATABASE_URL and run migrations

In a **second terminal** (with port-forward still running):

```bash
export DATABASE_URL="postgresql://clusteradmin:YOUR_PASSWORD@localhost:5432/integrationhub"

# Run all pending migrations (from repo root)
alembic -c apps/api/alembic.ini upgrade head

# Check current revision
alembic -c apps/api/alembic.ini current

# Show migration history
alembic -c apps/api/alembic.ini history
```

**PowerShell (Windows):**
```powershell
$env:DATABASE_URL = "postgresql://clusteradmin:YOUR_PASSWORD@localhost:5432/integrationhub"
alembic -c apps/api/alembic.ini upgrade head
```

### Step 5: Stop port-forward

Press `Ctrl+C` in the port-forward terminal when done.

## Environment Variables

| Variable      | Required | Description                                  |
|---------------|----------|----------------------------------------------|
| DATABASE_URL  | Yes      | PostgreSQL connection string, e.g. `postgresql://user:pass@host:5432/dbname` |

## One-liner (with AWS CLI)

If you have `jq` and the secret ARN:

```bash
# 1. Start port-forward in background or another terminal first, then:
export SECRET_ARN="<your-database-secret-arn>"
export DATABASE_URL=$(aws secretsmanager get-secret-value --secret-id $SECRET_ARN --query SecretString --output text | jq -r '"postgresql://\(.username):\(.password)@localhost:5432/\(.dbname // "integrationhub")"')
alembic -c apps/api/alembic.ini upgrade head
```
