# Integration Hub - Local dev targets
# Prereqs: Docker, make. For local-db-init: pip install -e ".[dev]"
# UI: Node.js, npm. Run `make install-ui` before first dev.

.PHONY: local-up local-down local-db-init local-sync-db local-seed-db local-logs local-health install-ui dev-ui dev-ui-aws dev-admin dev-partners build-ui

local-up:
	@if command -v docker >/dev/null 2>&1; then \
		docker compose up -d; \
		echo "Waiting for DB..."; \
		sleep 3; \
	else \
		echo "Docker not available; continuing in DB-only/local API mode."; \
	fi
	$(MAKE) local-sync-db
	@test -d apps/web-cip/node_modules || npm install
	@echo "Starting Admin + Vendor portals with AWS/Okta settings..."
	@bash tooling/scripts/run_ui_aws.sh &
	@echo "Hub API: http://localhost:8080 | Admin: http://localhost:5173 | Vendor: http://localhost:5174"

local-down:
	@-lsof -ti:5173 | xargs kill -9 2>/dev/null || true
	@-lsof -ti:5174 | xargs kill -9 2>/dev/null || true
	@if command -v docker >/dev/null 2>&1; then \
		docker compose down -v; \
	else \
		echo "Docker not available; skipped docker compose down -v."; \
	fi

local-db-init:
	@echo "Running migrations and seed..."
	PGHOST=localhost PGPORT=5434 PGUSER=hub PGPASSWORD=hub PGDATABASE=hub \
	DATABASE_URL=postgresql://hub:hub@localhost:5434/hub \
	python tooling/scripts/local_db_init.py

local-sync-db:
	@echo "Syncing migrations only (no seed, no container changes)..."
	PGHOST=localhost PGPORT=5434 PGUSER=hub PGPASSWORD=hub PGDATABASE=hub \
	DATABASE_URL=postgresql://hub:hub@localhost:5434/hub \
	python tooling/scripts/local_db_init.py --migrate-only

local-seed-db:
	@echo "Seeding local DB only..."
	PGHOST=localhost PGPORT=5434 PGUSER=hub PGPASSWORD=hub PGDATABASE=hub \
	DATABASE_URL=postgresql://hub:hub@localhost:5434/hub \
	python tooling/scripts/local_db_init.py --seed-only

local-logs:
	@if command -v docker >/dev/null 2>&1; then \
		docker compose logs -f; \
	else \
		echo "Docker not available; no compose logs to stream."; \
	fi

local-health:
	@curl -s http://localhost:8080/health | python -m json.tool

# UI (frontend) targets - run after make local-up for full stack
install-ui:
	npm install

# Default UI run: both portals with AWS settings (from env-config or .env.aws)
dev-ui dev-ui-aws:
	@echo "Starting Admin + Vendor portals with AWS settings..."
	@test -d apps/web-cip/node_modules || npm install
	@bash tooling/scripts/run_ui_aws.sh

dev-admin:
	cd apps/web-cip && npm run dev
# Admin: http://localhost:5173

dev-partners:
	cd apps/web-partners && npm run dev
# Vendor: http://localhost:5174

build-ui:
	cd apps/web-cip && npm run build
	cd apps/web-partners && npm run build
