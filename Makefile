# ============================================================
# Makefile - HUBapp Template
# ============================================================
# Usage:
#   make help          Afficher l'aide
#   make dev           Lancer en mode développement (hot-reload + HMR)
#   make up-dev        Mode développement en arrière-plan
#   make up            Démarrer en mode production
#   make down          Arrêter les services
#   make test          Lancer les tests
#   make logs          Voir les logs
# ============================================================

# Charger les variables .env si le fichier existe
ifneq (,$(wildcard ./.env))
	include .env
	export
endif

.PHONY: help sync-env sync-hub-host ssl dev up-dev build up down down-dev \
        restart restart-api restart-frontend logs logs-api logs-db \
        ensure-api-fresh test test-seq test-cov test-docker test-docker-cov \
        health health-detailed version \
        db-shell clean clean-all init ai-index bump-patch bump-minor bump-major \
        refresh-design-seed sync-hub-tooling sync-hub-tooling-check

COMPOSE      = docker compose -f docker-compose.yml
COMPOSE_DEV  = docker compose -f docker-compose.yml -f docker-compose.dev.yml

# Stamp du dernier rebuild api assuré (consommé par check_image_freshness.py)
STAMP_FILE   = .api-image.stamp

APP_SLUG ?= mon-app

help: ## Afficher cette aide
	@echo "╔══════════════════════════════════════════════════╗"
	@echo "║          HUBapp Template - Commandes            ║"
	@echo "╚══════════════════════════════════════════════════╝"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# === SSL / HTTPS ===

update-env: ## Fusionner les nouvelles clés du .env.example dans .env (sauvegarde auto, valeurs existantes préservées)
	@python3 scripts/update_env.py

sync-env: ## Allouer les ports via le Hub si absents, puis synchroniser FRONTEND_HTTPS_PORT et APP_VERSION
	@if [ ! -f .env ]; then cp .env.example .env && echo "🆕 Premier démarrage : .env créé depuis .env.example — adaptez APP_SLUG, HUB_HOST et les secrets (POSTGRES_PASSWORD) si besoin."; fi
	@python3 ACTIONS/PYTHON/sync_hub_host.py --quiet
	@python3 ACTIONS/PYTHON/allocate_ports.py || { echo "❌ Allocation des ports échouée"; exit 1; }
	@frontend_port=$$(grep -E '^FRONTEND_PORT=' .env | tail -n 1 | cut -d '=' -f2); \
	if ! echo "$$frontend_port" | grep -Eq '^[0-9]+$$'; then \
		echo "❌ FRONTEND_PORT invalide dans .env: '$$frontend_port'"; \
		exit 1; \
	fi; \
	app_version=$$(cat VERSION 2>/dev/null | tr -d '\r\n'); \
	if ! echo "$$app_version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$'; then \
		echo "❌ VERSION invalide: '$$app_version'"; \
		exit 1; \
	fi; \
	frontend_https_port=$$((frontend_port + 1)); \
	if grep -q "^FRONTEND_HTTPS_PORT=" .env 2>/dev/null; then \
		sed -i "s/^FRONTEND_HTTPS_PORT=.*/FRONTEND_HTTPS_PORT=$$frontend_https_port/" .env; \
	else \
		echo "" >> .env; \
		echo "FRONTEND_HTTPS_PORT=$$frontend_https_port" >> .env; \
	fi; \
	if grep -q "^APP_VERSION=" .env 2>/dev/null; then \
		sed -i "s/^APP_VERSION=.*/APP_VERSION=$$app_version/" .env; \
	else \
		echo "APP_VERSION=$$app_version" >> .env; \
	fi; \
	echo "🔢 Ports synchronisés: HTTP=$$frontend_port, HTTPS=$$frontend_https_port"; \
	echo "🏷️ Version synchronisée: $$app_version"

sync-hub-host: ## Synchroniser l'IP du Hub (découverte auto, ou make sync-hub-host HUB_HOST=x.x.x.x)
ifeq ($(origin HUB_HOST),command line)
	@python3 ACTIONS/PYTHON/sync_hub_host.py --hub-host $(HUB_HOST)
else
	@python3 ACTIONS/PYTHON/sync_hub_host.py
endif

ssl: ## Générer les certificats SSL (pour HTTPS)
	@bash scripts/generate-ssl.sh

# === DÉVELOPPEMENT ===

dev: sync-env ## Lancer en mode développement (hot-reload backend + HMR frontend)
	$(COMPOSE_DEV) up --build -d
	$(COMPOSE_DEV) logs -f

up-dev: sync-env ## Démarrer le mode développement en arrière-plan
	$(COMPOSE_DEV) up --build -d

build: sync-env ## Construire les images Docker
	$(COMPOSE) build
	@touch $(STAMP_FILE)

up: sync-env ## Démarrer les services en arrière-plan (production)
	@frontend_port=$$(grep -E '^FRONTEND_PORT=' .env | tail -n 1 | cut -d '=' -f2); \
	frontend_https_port=$$(grep -E '^FRONTEND_HTTPS_PORT=' .env | tail -n 1 | cut -d '=' -f2); \
	https_enabled=$$(grep -E '^HTTPS_ENABLED=' .env | tail -n 1 | cut -d '=' -f2); \
	echo "🚀 Démarrage: HTTP=$$frontend_port, HTTPS=$$frontend_https_port, HTTPS_ENABLED=$$https_enabled"
	@https_enabled=$$(grep -E '^HTTPS_ENABLED=' .env | tail -n 1 | cut -d '=' -f2); \
	if [ "$$https_enabled" != "false" ]; then \
		bash scripts/generate-ssl.sh; \
		$(COMPOSE) -f docker-compose.https.yml up -d; \
	else \
		$(COMPOSE) up -d; \
	fi

down: ## Arrêter tous les services (prod ou dev)
	$(COMPOSE) down

down-dev: ## Arrêter les services lancés en mode dev
	$(COMPOSE_DEV) down

restart: ## Redémarrer tous les services
	$(COMPOSE) restart

restart-api: ## Redémarrer uniquement l'API
	$(COMPOSE) restart api

restart-frontend: ## Redémarrer uniquement le frontend
	$(COMPOSE) restart frontend

# === LOGS ===

logs: ## Voir les logs de tous les services
	$(COMPOSE) logs -f

logs-api: ## Voir les logs de l'API uniquement
	$(COMPOSE) logs -f api

logs-db: ## Voir les logs de PostgreSQL
	$(COMPOSE) logs -f postgres

# === TESTS ===

XDIST_WORKERS ?= auto

test: ## Lancer les tests pytest sur l'hôte (SQLite en mémoire, rapide, parallèle)
	cd backend && python3 -m pytest -n $(XDIST_WORKERS) -v

test-seq: ## Tests pytest séquentiels (debug flaky / ordre-dépendant)
	cd backend && python3 -m pytest -v

lint-classes: ## Détecter les classes fantômes (JSX vs build HUBCSS — voir HUBCSS/docs/CASCADE.md)
	cd frontend && npm run lint:classes

verify-ui: ## Smoke UI par styles calculés (Playwright) — make verify-ui APP=../MON_APP/frontend
	cd frontend && node scripts/verify-ui.mjs $(APP)

test-cov: ## Lancer les tests avec couverture (hôte)
	cd backend && python3 -m pytest -n $(XDIST_WORKERS) --cov=. --cov-report=html -v

ensure-api-fresh: ## (interne) Rebuilder l'image api si les sources sont plus récentes
	@case "$(MAKEFLAGS)" in *n*) echo "[dry-run] ensure-api-fresh sauté"; exit 0;; esac; \
	python3 ACTIONS/PYTHON/check_image_freshness.py; rc=$$?; \
	if [ $$rc -eq 1 ]; then \
		$(MAKE) sync-env && $(COMPOSE) build api && $(COMPOSE) up -d api && touch $(STAMP_FILE); \
	elif [ $$rc -ne 0 ]; then exit $$rc; fi

test-docker: ensure-api-fresh ## Lancer pytest dans le conteneur api (env Docker, image runtime)
	$(COMPOSE) exec api python -m pytest -n $(XDIST_WORKERS) -v

test-docker-cov: ensure-api-fresh ## Pytest + couverture dans le conteneur api
	$(COMPOSE) exec api python -m pytest -n $(XDIST_WORKERS) --cov=. --cov-report=term-missing -v

# === SANTÉ ===

health: ## Vérifier le health check de l'API
	@curl -sf http://localhost:$${API_PORT:-9045}/api/health | python3 -m json.tool || echo "❌ API non accessible"

health-detailed: ## Health check détaillé
	@curl -sf http://localhost:$${API_PORT:-9045}/api/health/detailed | python3 -m json.tool || echo "❌ API non accessible"

version: ## Afficher la version
	@cat VERSION

# === BASE DE DONNÉES ===

db-shell: ## Ouvrir un shell PostgreSQL
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-app_user} -d $${POSTGRES_DB:-app_db}

# === NETTOYAGE ===

clean: ## Supprimer les conteneurs, volumes et caches
	$(COMPOSE) down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true

clean-all: clean ## Nettoyage complet (+ images Docker)
	$(COMPOSE) down -v --rmi local

# === INITIALISATION ===

init: ## Initialiser une nouvelle app depuis le template (déprécié : utilisez ACTIONS/PYTHON/INITIALISE.py)
	python3 ACTIONS/PYTHON/INITIALISE.py

ai-index: ## Régénérer AI_INDEX.md (carte symboles pour assistants IA)
	python3 scripts/generate_ai_index.py

# === VERSION ===

bump-patch: ## Incrémenter la version patch (x.y.Z)
	python3 scripts/bump_version.py patch

bump-minor: ## Incrémenter la version minor (x.Y.0)
	python3 scripts/bump_version.py minor

bump-major: ## Incrémenter la version major (X.0.0)
	python3 scripts/bump_version.py major

# === DESIGN SYSTEM (HUBCSS seed) ===

HUBCSS_DIR ?= ../HUBCSS
DESIGN_SEED := frontend/public/design-system/current

refresh-design-seed: ## Régénérer le seed HUBCSS local depuis $(HUBCSS_DIR)/dist
	@test -f "$(HUBCSS_DIR)/dist/global.css" || { echo "❌ $(HUBCSS_DIR)/dist introuvable. Lancez 'npm run build' dans HUBCSS."; exit 1; }
	@mkdir -p "$(DESIGN_SEED)/bootstrap-icons/fonts" "$(DESIGN_SEED)/icons"
	@cp "$(HUBCSS_DIR)/dist/global.css" "$(DESIGN_SEED)/global.css"
	@cp "$(HUBCSS_DIR)/dist/fonts.css" "$(DESIGN_SEED)/fonts.css"
	@cp "$(HUBCSS_DIR)/dist/bootstrap-icons/bootstrap-icons.css" "$(DESIGN_SEED)/bootstrap-icons/bootstrap-icons.css"
	@cp "$(HUBCSS_DIR)/dist/bootstrap-icons/fonts/bootstrap-icons.woff" "$(DESIGN_SEED)/bootstrap-icons/fonts/bootstrap-icons.woff"
	@cp "$(HUBCSS_DIR)/dist/bootstrap-icons/fonts/bootstrap-icons.woff2" "$(DESIGN_SEED)/bootstrap-icons/fonts/bootstrap-icons.woff2"
	@cp "$(HUBCSS_DIR)/dist/icons/lucide.svg" "$(DESIGN_SEED)/icons/lucide.svg"
	@echo "✅ Seed HUBCSS rafraîchi dans $(DESIGN_SEED)"

# === OUTILLAGE HUB (MCP + plugin opencode) ===
# Sources de vérité : MCP = dépôt dédié $(HUB_MCP_SRC) ; plugin = $(HUB_STACK_DIR)

HUB_STACK_DIR ?= ..
HUB_MCP_SRC ?= ../hub-mcp/hub_mcp

sync-hub-tooling: ## Resynchroniser hub_mcp (depuis $(HUB_MCP_SRC)) + plugin opencode (depuis $(HUB_STACK_DIR))
	@test -f "$(HUB_MCP_SRC)/server.py" || { echo "❌ $(HUB_MCP_SRC) introuvable (dépôt hub-mcp)"; exit 1; }
	@test -f "$(HUB_STACK_DIR)/.opencode/plugins/hub.ts" || { echo "❌ $(HUB_STACK_DIR)/.opencode/plugins/hub.ts introuvable"; exit 1; }
	@mkdir -p hub_mcp/tests .opencode/plugins
	@cp "$(HUB_MCP_SRC)/"*.py hub_mcp/
	@cp "$(HUB_MCP_SRC)/tests/"*.py hub_mcp/tests/
	@cp "$(HUB_STACK_DIR)/.opencode/plugins/hub.ts" .opencode/plugins/hub.ts
	@find hub_mcp -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Outillage Hub synchronisé (MCP: $(HUB_MCP_SRC), plugin: $(HUB_STACK_DIR))"

sync-hub-tooling-check: ## Vérifier que la copie hub_mcp + plugin est synchro avec les sources (CI)
	@diff -r -x __pycache__ -x .pytest_cache "$(HUB_MCP_SRC)" hub_mcp >/dev/null 2>&1 \
		&& diff "$(HUB_STACK_DIR)/.opencode/plugins/hub.ts" .opencode/plugins/hub.ts >/dev/null 2>&1 \
		&& echo "✅ Outillage Hub synchronisé" \
		|| { echo "❌ Dérive détectée — lancez 'make sync-hub-tooling'"; exit 1; }
