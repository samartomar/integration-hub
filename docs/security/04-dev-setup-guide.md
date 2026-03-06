# Dev Setup Guide

## Prerequisites

- Node.js, Python 3.11+
- Docker (for local DB)
- Auth0 dev tenant

## 1. Clone and install

```bash
git clone <repo>
cd py-poc
pip install -r requirements.txt
npm install  # in apps/web-cip, apps/web-partners
```

## 2. Environment variables

Create `.env.local` (see `docs/read-this-first/06_LOCAL_DEV.md` for full list):

```
AUTH_BYPASS=true          # Local dev: skip auth
DB_URL=postgresql://...
```

## 3. Database

```bash
docker-compose up -d postgres
# Run migrations
# Seed: tooling/scripts/seed_local.py or tooling/scripts/local_seed.sql
```

## 4. Start local API

```bash
# From repo root: make local-up (starts hub-api in Docker)
# Or run local API only: uvicorn apps.api.local.app:app --host 0.0.0.0 --port 8080
```

## 5. Auth0 (when testing JWT)

- Create Auth0 API with audience
- Create SPA app; add `http://localhost:5173` to redirect URIs
- Create M2M app for server testing
- Set `VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID`, `VITE_AUTH0_AUDIENCE` in frontend `.env`

## Confirmation

Before running dev setup commands that alter your environment, review `CURSOR_EXECUTE.md`.
