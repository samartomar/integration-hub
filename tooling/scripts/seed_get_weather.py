#!/usr/bin/env python3
"""Add GET_WEATHER operation for local integration tests."""
import os
import psycopg2

url = os.environ.get("DATABASE_URL", "postgresql://clusteradmin:localdev@localhost:5432/integrationhub")
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute(
    "INSERT INTO control_plane.operations (operation_code, description, canonical_version, is_async_capable, is_active) "
    "VALUES ('GET_WEATHER', 'Get weather', 'v1', false, true) "
    "ON CONFLICT (operation_code) DO UPDATE SET is_active = true"
)
conn.commit()
conn.close()
print("GET_WEATHER added")
