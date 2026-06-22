# ============================================================
# Makefile - HUBapp Template
# ============================================================
# Usage:
#   make help          Afficher l'aide
#   make dev           Lancer en mode développement
#   make build         Construire les images Docker
#   make up            Démarrer les services
#   make down          Arrêter les services
#   make test          Lancer les tests
#   make logs          Voir les logs
# ============================================================

.PHONY: help dev build up down restart logs test lint clean refresh-design-seed

# Charger les variables .env si le fichier existe
ifneq (,$(wildcard ./.env))
	include .env
	export
endif

APP_SLUG ?= mon-app

help: ## Afficher cette aide
	@echo "╔══════════════════════════════════════════════════╗"
	@echo "║          HUBapp Template - Commandes            ║"
	@echo "╚══════════════════════════════════════════════════╝"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# === SSL / HTTPS ===

sync-env: ## Allouer les ports via le Hub si absents, puis synchroniser FRONTEND_HTTPS_PORT et APP_VERSION
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

ssl: ## Générer les certificats SSL (pour HTTPS)
	@bash scripts/generate-ssl.sh

# === DÉVELOPPEMENT ===

dev: sync-env ## Lancer en mode développement (rebuild + logs)
	@https_enabled=$$(grep -E '^HTTPS_ENABLED=' .env | tail -n 1 | cut -d '=' -f2); \
	if [ "$$https_enabled" = "true" ]; then bash scripts/generate-ssl.sh; fi
	docker compose up --build -d
	docker compose logs -f

build: sync-env ## Construire les images Docker
	docker compose build

up: sync-env ## Démarrer les services en arrière-plan
	@frontend_port=$$(grep -E '^FRONTEND_PORT=' .env | tail -n 1 | cut -d '=' -f2); \
	frontend_https_port=$$(grep -E '^FRONTEND_HTTPS_PORT=' .env | tail -n 1 | cut -d '=' -f2); \
	https_enabled=$$(grep -E '^HTTPS_ENABLED=' .env | tail -n 1 | cut -d '=' -f2); \
	echo "🚀 Démarrage: HTTP=$$frontend_port, HTTPS=$$frontend_https_port, HTTPS_ENABLED=$$https_enabled"
	@https_enabled=$$(grep -E '^HTTPS_ENABLED=' .env | tail -n 1 | cut -d '=' -f2); \
	if [ "$$https_enabled" = "true" ]; then bash scripts/generate-ssl.sh; fi
	docker compose up -d

down: ## Arrêter tous les services
	docker compose down

restart: ## Redémarrer tous les services
	docker compose restart

restart-api: ## Redémarrer uniquement l'API
	docker compose restart api

restart-frontend: ## Redémarrer uniquement le frontend
	docker compose restart frontend

# === LOGS ===

logs: ## Voir les logs de tous les services
	docker compose logs -f

logs-api: ## Voir les logs de l'API uniquement
	docker compose logs -f api

logs-db: ## Voir les logs de PostgreSQL
	docker compose logs -f postgres

# === TESTS ===

test: ## Lancer les tests pytest sur l'hôte (SQLite en mémoire, rapide)
	cd backend && python -m pytest -v

test-cov: ## Lancer les tests avec couverture (hôte)
	cd backend && python -m pytest --cov=. --cov-report=html -v

test-docker: ## Lancer pytest dans le conteneur api (env Docker, image runtime)
	docker compose exec api python -m pytest -v

test-docker-cov: ## Pytest + couverture dans le conteneur api
	docker compose exec api python -m pytest --cov=. --cov-report=term-missing -v

# === SANTÉ ===

health: ## Vérifier le health check de l'API
	@curl -sf http://localhost:$${API_PORT:-9045}/api/health | python3 -m json.tool || echo "❌ API non accessible"

health-detailed: ## Health check détaillé
	@curl -sf http://localhost:$${API_PORT:-9045}/api/health/detailed | python3 -m json.tool || echo "❌ API non accessible"

version: ## Afficher la version
	@cat VERSION

# === BASE DE DONNÉES ===

db-shell: ## Ouvrir un shell PostgreSQL
	docker compose exec postgres psql -U $${POSTGRES_USER:-app_user} -d $${POSTGRES_DB:-app_db}

# === NETTOYAGE ===

clean: ## Supprimer les conteneurs, volumes et caches
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true

clean-all: clean ## Nettoyage complet (+ images Docker)
	docker compose down -v --rmi local

# === INITIALISATION ===

init: ## Initialiser une nouvelle app depuis le template (déprécié : utilisez ACTIONS/PYTHON/INITIALISE.py)
	python ACTIONS/PYTHON/INITIALISE.py

ai-index: ## Régénérer AI_INDEX.md (carte symboles pour assistants IA)
	python scripts/generate_ai_index.py

# === VERSION ===

bump-patch: ## Incrémenter la version patch (x.y.Z)
	python scripts/bump_version.py patch

bump-minor: ## Incrémenter la version minor (x.Y.0)
	python scripts/bump_version.py minor

bump-major: ## Incrémenter la version major (X.0.0)
	python scripts/bump_version.py major

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
