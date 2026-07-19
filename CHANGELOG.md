# Changelog - HUBapp Template

Historique des modifications du template d'application Hub.

Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

---

## [Unreleased]

## [2.6.1] - 19 juillet 2026

### ⚡ Sécurité outbox et stabilité AuthProvider

- **Corrigé** : outbox — seules les réponses HTTP `2xx` sont livrées ; les `4xx` restent en `failed` (retry).
- **Corrigé** : `cleanup_old_messages()` commit désormais la purge.
- **Corrigé** : AuthProvider — l'effet de refresh proactif est déplacé après la déclaration de `refreshAccessToken`, supprimant l'erreur TDZ (ReferenceError) au rendu.
- **Ajouté** : `_do_register()` transmet un token Bearer M2M en cache lors d'une réinscription.
- **Documentation** : procédure canari volontaire `MIGRATION_M2M_CANARY.md`.
- **Tests** : +2 tests (_do_register avec/sans credentials), 1 test outbox réaligné (4xx → failed) ; 135 passed.

## [2.6.0] - 18 juillet 2026

### ⚡ Déclaration et suivi des dépendances M2M

- **Ajouté** : lecture de `depends.yaml` par `HubClient`, avec dépendance PyYAML.
- **Ajouté** : envoi non bloquant des dépendances déclarées pendant l'inscription de l'application au Hub.
- **Ajouté** : `HubClient.report_sync()` pour remonter les synchronisations M2M réussies au Hub.
- **Ajouté** : helper `_push_deps_to_hub()` et prise en charge des credentials M2M mis en cache dans le registre.
- **Documentation** : ajout du skill `app-dependencies` pour déclarer et instrumenter les dépendances inter-apps.

## [2.5.0] - 10 juillet 2026

### ⚡ Catalogue M2M exportable (auto-introspection)

- **Ajouté** : `GET /api/m2m/catalog` (auth service account) — auto-introspection de la surface d'API de l'app (paths, méthodes, schémas résolus, niveaux d'auth). Destiné à être agrégé par le Hub pour produire un export global du parc.
- **Ajouté** : module `backend/m2m_catalog.py` — `deduce_auth_level(route)` (déduction du niveau d'auth via l'arbre des dépendances), `resolve_refs(spec)` (inlining des `$ref` OpenAPI + détection de cycles), `build_app_catalog(app)` (assemblage du catalogue).
- **Ajouté** : tagging `__auth_level__`/`__auth_roles__` sur les closures `require_role`/`require_any_role`/`require_service_account` (`hub_auth.py`) pour permettre l'introspection fiable du niveau d'auth de chaque route.
- **Docs** : documentation des endpoints dans `API.md` + nouvelle « Phase E » dans le skill `hub-m2m-communication`.

## [2.4.4] - 6 juillet 2026

### 🐛 Corrections (tests)
- **Tests services** : activation de `ENABLE_DEMO_ENDPOINTS` dans `conftest.py` (19 tests `test_services.py` désormais verts).
- **Tests backup** : `test_backup.py` réaligné sur le format générique v3.0 (`tables`/`total_tables`/`total_rows`) et `utils.human_readable_size` correctement référencée.

### 🐛 Corrections (code)
- **Backup** : introspection DB dialect-agnostique via SQLAlchemy `Inspector` (remplace `information_schema`/`pg_*` Postgres-only → tests SQLite valides + robustesse Postgres).
- **Restore** : `SET CONSTRAINTS ALL DEFERRED` restreint à PostgreSQL (SQLite ignoré).
- **Models** : `OutboxMessage.headers` `default=dict` (mutable default footgun).
- **hub_auth** : retrait du fallback JWKS mort dans `_try_decode` (cascade directe vers PEM).
- **Compose** : port 443 conditionnel via `docker-compose.https.yml` (plus de crash si `FRONTEND_HTTPS_PORT` vide) + fallback `APP_SLUG` sur `POSTGRES_HOST`.
- **M2MTests** : variables CSS `--border-color`/`--primary-color` → `--border`/`--accent` (alias HUBCSS réels).

### 🔧 Chores
- **Makefile** : toutes les cibles `python` → `python3` (cohérence tooling, robustesse distros).
- **Dépendances** : retrait de `psycopg2-binary` inutilisée (stack 100% async/asyncpg).
- **bump_version** : format de date portable (`lstrip("0")` au lieu de `%-d` GNU-only).

### 📝 Docs
- **CHANGELOG** : réinsertion de l'entrée `[2.4.2]` manquante.

## [2.4.3] - 5 juillet 2026

### ⚡ Skills .opencode centralisés
- **9 skills « app »** (`backup-restore-ops`, `badge-search-system`,
  `cache-busting-deployment`, `deploy-troubleshoot`, `frontend-crud-page`,
  `hub-messages-integration`, `react-list-rendering`, `release-sync`,
  `verify-feature`) déplacés du méta-repo POULIDOR vers
  `.opencode/skills/`. Leurs chemins relatifs `../../../` résolvent
  désormais dans le contexte de l'app.
- `opencode.json` mis à jour avec `skills.paths: [.opencode/skills]`.

### Correctif
- **Double `apply_migrations()`** retiré dans `backend/main.py` (appelé
  deux fois consécutivement, non bloquant mais incorrect).
- **`.instructions.md`** : références Tailwind retirées (stack retirée
  en `cc56c85`) et remplacées par HUBCSS ; chemin `index.css` corrigé
  en `app.css`.
- **Seed HUBCSS régénéré** : `global.css` 16 Ko → 38 Ko (tokens
  `--hub-space-*`, nouveaux composants 0.2.x : Timeline, StatCard,
  Skeleton, EmptyState, Search*, etc.).

### Interne
- **Versions synchronisées** : `bump_version.py` appliqué, `package.json`,
  `.env.example` et `docs/API.md` alignés sur `VERSION`.
- `frontend/src/context/AuthContext.jsx` modifié (SSE `?token=` pour
  compatibilité EventSource, en attente du fix côté Hub v3.9.0).

### Correctif
- **MCP hub** : ajout d'un micro `opencode.json` (contenant uniquement le bloc
  `mcp.hub`) pour câbler le serveur MCP propre au template. Le dev-interface
  générique (skills, plugins) reste centralisé dans POULIDOR.

## [2.4.2] - 28 juin 2026

### Correctif
- **MCP hub** : ajout d'un micro `opencode.json` (contenant uniquement le bloc
  `mcp.hub`) pour câbler le serveur MCP propre au template. Le dev-interface
  générique (skills, plugins) reste centralisé dans POULIDOR.

## [2.4.1] - 28 juin 2026

### 🗑️ Centralisation du dev-interface (vers POULIDOR)

- **Retrait** : `opencode.json`, `.opencode/`, `AGENTS.md`, `.github/` (instructions / skills / prompts), `AI_INDEX.md`. Le tooling de dev est désormais centralisé dans le méta-dépôt POULIDOR ; les apps générées par ce template restent propres. Conservés : `INITIALISE`/`ACTIONS` (bootstrap), `backend/`, `frontend/`, `hub_mcp/`, `scripts/`.

### ✨ Nouvelles fonctionnalités

- **Nouveau** : Cibles Make `test-docker` / `test-docker-cov` qui lancent pytest dans le conteneur `api` (image runtime, env Postgres réel)
- **Nouveau** : Cible Make `ai-index` qui régénère `AI_INDEX.md` via `scripts/generate_ai_index.py`

### 🔧 Modifications code

- **Refactor** : `index_Test.py` (racine) déplacé vers `scripts/generate_ai_index.py` ; chemin de sortie résolu par rapport au script (peu importe le cwd)
- **Doc** : `AGENTS.md` pointe désormais vers la skill `verify-feature` pour toute validation post-changement
- **Doc** : `docs/HTTPS.md` ne référence plus `make start` / `start.sh` ; remplacé par `make dev`

### 🗑️ Suppression

- **Suppression** : `presentation.html` (démo non utilisée par le template)
- **Suppression** : `start.sh` (redondant avec `make dev` / `make up` qui appellent déjà `sync-env` et la génération SSL)

---

## [2.4.0] - 12 avril 2026

### ✨ Nouvelles fonctionnalités

- **Nouveau** : Support des migrations SQL applicatives via `backend/migrations/` avec une première migration `001_fix_datetime_timezone.sql`
- **Nouveau** : Endpoint `POST /api/tests/messages/send` pour envoyer un message de test via le compte M2M de l'application
- **Nouveau** : Scripts `init_new_app.sh` et `init_new_app.bat` qui transmettent désormais les options au script Python (`--clean`, `--tailwind`)

### 🔧 Modifications code

- **Amélioration** : Reconnexion Hub et gestion du token M2M renforcées pour mieux supporter les resynchronisations et les services distants
- **Amélioration** : Normalisation des datetimes en UTC timezone-aware avec migration des colonnes vers `TIMESTAMPTZ`
- **Amélioration** : Synchronisation de `APP_VERSION` étendue à `.env` et `.env.example` dans `bump_version.py`
- **Amélioration** : Limites mémoire Docker fixées à `512M` pour les services principaux dans `docker-compose.yml`
- **Refactor** : Réorganisation backend/frontend pour améliorer la lisibilité et préparer l'intégration des évolutions de la branche `v2`

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `backend/database.py` | Initialisation de la base enrichie avec exécution des migrations SQL |
| `backend/migrations/001_fix_datetime_timezone.sql` | Migration de correction des colonnes datetime vers un stockage timezone-aware |
| `backend/hub_auth.py` | Fonctions utilitaires UTC et amélioration de la logique de reconnexion Hub |
| `backend/hub_client.py` | Gestion M2M renforcée, normalisation des expirations de token et de la découverte de services |
| `backend/routes/tests.py` | Nouvel endpoint `POST /api/tests/messages/send` pour l'envoi de messages de test via le Hub |
| `backend/tests/test_services.py` | Couverture des nouveaux scénarios M2M et de l'envoi de message de test |
| `scripts/bump_version.py` | Synchronisation de `APP_VERSION` dans `.env` et `.env.example` |
| `scripts/init_new_app.py` | Gestion plus robuste des modes `--clean` et `--tailwind`, documentation d'initialisation mise à jour |
| `scripts/init_new_app.sh` | Transmission de tous les arguments au script Python |
| `scripts/init_new_app.bat` | Transmission de tous les arguments au script Python sur Windows |
| `docker-compose.yml` | Limites mémoire ajoutées et alignement avec les évolutions d'infrastructure récentes |
| `docs/API.md` / `docs/HUB_MESSAGES.md` / `docs/REMOTE_APPS.md` | Documentation mise à jour pour les messages Hub, les migrations et les applications distantes |

---

## [2.3.1] - 27 mars 2026

### 🐛 Corrections

- **Fix** : Synchronisation du port HTTPS avec `FRONTEND_PORT` dans la configuration, l'entrypoint frontend et le script d'initialisation
- **Fix** : Documentation HTTPS et README réalignés sur le comportement réel des ports exposés

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `.env.example` | Calcul et exposition cohérents du port HTTPS |
| `docker-compose.yml` | Ports HTTPS alignés avec la configuration frontend |
| `frontend/docker-entrypoint.sh` | Gestion corrigée de la configuration des ports pour le frontend |
| `scripts/init_new_app.py` | Génération des ports HTTPS synchronisée avec `FRONTEND_PORT` |
| `README.md` / `docs/HTTPS.md` / `docs/API.md` | Documentation mise à jour pour refléter le mapping HTTPS réel |

---

## [2.3.0] - 1 mars 2026

### ✨ Nouvelles fonctionnalités

- **Nouveau** : Support HTTPS renforcé avec génération automatisée des certificats SSL
- **Nouveau** : Documentation dédiée pour l'activation HTTPS et la génération de certificats locaux

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `scripts/generate-ssl.sh` | Génération automatisée des certificats de développement |
| `ssl/openssl.cnf` | Configuration OpenSSL dédiée au template |
| `nginx.conf` | Adaptations pour servir le frontend avec la configuration HTTPS |
| `frontend/docker-entrypoint.sh` | Préparation du frontend au mode HTTPS |
| `frontend/src/config.js` / `frontend/config.js` | Exposition de la configuration HTTPS côté frontend |
| `backend/config.py` / `backend/hub_auth.py` | Lecture et utilisation des paramètres HTTPS côté backend |
| `docs/HTTPS.md` / `docs/API.md` | Documentation de la mise en place HTTPS |
| `Makefile` / `start.sh` | Commandes et démarrage local mis à jour |

---

## [2.2.2] - 24 février 2026

### 🐛 Corrections

- **Fix** : Suppression des rôles globaux du payload du token Hub afin de limiter les données exposées au frontend
- **Fix** : Adaptation du contexte d'authentification, des schémas et des tests de services à la nouvelle structure de token

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `backend/hub_auth.py` | Payload du token épuré des rôles globaux |
| `backend/schemas.py` | Schémas ajustés à la nouvelle structure d'authentification |
| `backend/routes/tests.py` | Endpoints de tests adaptés au nouveau format de token |
| `backend/tests/conftest.py` | Fixtures mises à jour pour refléter le payload simplifié |
| `frontend/src/context/AuthContext.jsx` | Consommation frontend du token Hub alignée avec le nouveau payload |
| `frontend/src/components/M2MTests.jsx` / `frontend/src/components/UserCard.jsx` | Affichage frontend ajusté |

---

## [2.2.1] - 23 février 2026

### 🐛 Corrections

- **Fix** : Gestion des datetimes backend rendue timezone-aware pour éviter les incohérences entre JWT, base de données et endpoints
- **Fix** : Contraintes explicites ajoutées aux dépendances backend pour fiabiliser les installations

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `backend/database.py` | Alignement de l'initialisation base de données avec les datetimes timezone-aware |
| `backend/hub_auth.py` / `backend/hub_client.py` | Calculs de dates et d'expiration normalisés |
| `backend/main.py` | Intégration des ajustements de configuration et de version |
| `backend/routes/items.py` / `backend/routes/m2m.py` / `backend/routes/preferences.py` / `backend/routes/test_data.py` | Ajustements transverses liés au nouveau traitement des dates |
| `backend/requirements.txt` | Contraintes de versions explicites pour les dépendances backend |
| `Dockerfile.backend` / `docker-compose.yml` / `.env.example` | Environnement aligné avec la nouvelle configuration |

---

## [2.1.0] - 17 février 2026

### 🐛 Corrections critiques

- **Fix** : Badge de version dupliqué ~20 fois dans `docs/API.md` — réécriture de `update_api_docs()` dans `bump_version.py` pour supprimer tous les doublons et ne garder qu'un seul badge
- **Fix** : Version `v1.7.0` codée en dur dans `init_new_app.py` pour le changelog généré
- **Fix** : `appSlug` jamais mis à jour dans `frontend/src/config.js`, `conftest.py`, et `test_m2m.py` lors de l'initialisation

### 🔒 Sécurité

- **Suppression** : Endpoint SSRF `/api/m2m/test-call` qui acceptait une URL arbitraire — vulnérabilité SSRF
- **Fix** : CORS `allow_origins=["*"]` remplacé par des origines calculées dynamiquement depuis les ports configurés. Support de la variable `CORS_ORIGINS` pour personnalisation
- **Fix** : Docstring `HubCredentials` corrigée (disait "JAMAIS sur disque" alors que les credentials sont sauvegardés sur disque)

### ✨ Nouvelles fonctionnalités

- **Nouveau** : Option `--clean` dans `init_new_app.py` qui supprime automatiquement tout le contenu de démonstration (modèles Item/TestData, endpoints de rôle, composants frontend, tests de démo)
- **Nouveau** : Module `backend/utils.py` avec fonctions utilitaires partagées (`human_readable_size`, `human_readable_duration`)
- **Nouveau** : Script d'init mis à jour (10 → 13 étapes) : met à jour `frontend/src/config.js`, les fixtures de test, et nettoie les fichiers obsolètes

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `scripts/bump_version.py` | Réécriture de `update_api_docs()` pour éviter la duplication de badges |
| `scripts/init_new_app.py` | +3 étapes (config.js, fixtures test, cleanup), option `--clean`, suppression frontend/config.js obsolète |
| `backend/main.py` | Suppression SSRF, CORS paramétrable, `datetime.utcnow()` → `datetime.now(timezone.utc)` |
| `backend/hub_client.py` | `fcntl` rendu optionnel (fallback Windows), docstring corrigée, suppression `datetime.utcnow()` |
| `backend/models.py` | `datetime.utcnow` → `lambda: datetime.now(timezone.utc)` dans les defaults |
| `backend/storage.py` | Import `human_readable_size` depuis `utils.py` |
| `backend/routes/backup.py` | Import fonctions utilitaires depuis `utils.py` |
| `backend/utils.py` | Nouveau module utilitaire partagé |
| `Dockerfile.frontend` | Suppression du `EXPOSE 80` dupliqué |
| `README.md` | Suppression références à `start.sh`, `start.ps1`, `auth.js` inexistants, correction des ports |
| `docs/API.md` | Nettoyage des ~20 badges dupliqués |
| `.gitignore` | Ajout `ssl/server.*`, `*.zip`, `postgres_data/`, `uploads/` |

### 🗑️ Suppressions

- `frontend/config.js` : vestige de la version vanilla JS, jamais importé par le code React (supprimé automatiquement par l'init)
- Endpoint `/api/m2m/test-call` : vulnérabilité SSRF
- Fonctions `_human_readable_size` et `_human_readable_duration` dupliquées dans `storage.py` et `backup.py` (extraites dans `utils.py`)

---

## [1.9.0] - 17 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Résilience du cache JWKS pour authentification Hub
Correction d'un problème critique : lorsque le Hub SSO ne répond pas après l'expiration du token JWT, l'authentification échouait complètement.

**Problème identifié :**
- La clé publique JWKS était stockée uniquement en mémoire
- Pas de TTL sur le cache mémoire (jamais rafraîchi)
- Aucun fallback si le Hub était indisponible

**Solution implémentée :**

1. **Persistance sur disque** (`hub_auth.py`)
   - Nouvelle fonction `_save_key_to_persistent_cache()` : sauvegarde la clé publique dans `storage/hub_jwks_cache.json`
   - Nouvelle fonction `_load_key_from_persistent_cache()` : charge la clé depuis le disque avec validation d'âge (max 7 jours)

2. **Cache mémoire avec TTL**
   - Ajout de `_cached_key_fetched_at` pour suivre l'âge du cache
   - TTL de 30 minutes (`JWKS_CACHE_TTL = 1800`)
   - Fonction `_is_cache_expired()` pour vérifier la validité

3. **Fallback en cascade dans `decode_token()`**
   - Tentative de récupération depuis le Hub
   - Si échec → utilise le cache mémoire (même expiré)
   - Si pas de cache mémoire → charge depuis le cache persistant
   - Erreur 503 seulement si aucun fallback disponible

4. **Résilience dans `verify_hub_token()`**
   - Si le client JWKS échoue (Hub down), utilise automatiquement le fallback
   - Retourne HTTP 503 au lieu de 401 si le Hub est down ET pas de cache

5. **Nouveaux endpoints de diagnostic** (`main.py`)
   - `GET /api/health/hub/jwks` : statut du cache JWKS (mémoire + disque)
   - `POST /api/health/hub/jwks/refresh` : force le rafraîchissement du cache

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `backend/hub_auth.py` | Logique de persistance et fallback en cascade |
| `backend/main.py` | Endpoints de diagnostic JWKS, intégration statut cache |
| `VERSION` | Mise à jour vers 1.9.0 |
| `CHANGELOG.md` | Documentation des changements |

### 🔧 Comportement

Le système suit maintenant cette stratégie de fallback :
```
Hub JWKS (30 min cache) → Cache mémoire → Cache disque (7 jours) → Clé PEM → Erreur 503
```

### 📋 Nouveaux endpoints

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/health/hub/jwks` | GET | Statut détaillé du cache JWKS |
| `/api/health/hub/jwks/refresh` | POST | Force le rafraîchissement du cache |

---

## [1.6.0] - 4 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Système de versionnage automatique
- **Nouveau** : Fichier `VERSION` comme source unique de vérité
- **Nouveau** : Script `scripts/bump_version.py` pour synchroniser les versions
- **Nouveau** : Endpoint `GET /api/version` pour consulter la version de l'API
- **Nouveau** : Labels de version dans les images Docker
- **Nouveau** : Hook Git `pre-commit` pour synchronisation automatique à chaque commit
- **Nouveau** : Script `scripts/install-hooks.sh` pour installer les hooks Git

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `VERSION` | Nouveau fichier contenant le numéro de version |
| `scripts/bump_version.py` | Script de gestion de version automatique |
| `scripts/install-hooks.sh` | Script d'installation des hooks Git |
| `scripts/git-hooks/pre-commit` | Hook de synchronisation automatique |
| `backend/config.py` | Ajout de `APP_VERSION` lu depuis VERSION |
| `backend/main.py` | Import de `APP_VERSION`, nouvel endpoint `/api/version` |
| `frontend/package.json` | Synchronisation version 1.0.0 -> 1.6.0 |
| `Dockerfile.backend` | Ajout ARG/LABEL version, copie de VERSION |
| `Dockerfile.frontend` | Ajout ARG/LABEL version |
| `docker-compose.yml` | Ajout ARG `APP_VERSION` dans les builds |
| `README.md` | Documentation du système de versionnage |
| `CHANGELOG.md` | Ajout format Keep a Changelog |

### 🔧 Installation (une seule fois après clone)

```bash
# Installer les hooks Git pour synchronisation automatique
./scripts/install-hooks.sh
```

### 📋 Checklist pour agents IA

- [ ] Utiliser `/api/version` pour vérifier la version déployée
- [ ] Les versions se synchronisent automatiquement au commit
- [ ] Mettre à jour le CHANGELOG.md avant chaque release

---

## [1.5.0] - 3 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Système de documentation API
- **Nouveau** : Endpoints de documentation avec changelog intégré
- **Nouveau** : `GET /api/docs/changelog` - Consulter le changelog complet
- **Nouveau** : `GET /api/docs/changelog/versions` - Liste des versions disponibles
- **Nouveau** : `GET /api/docs/changelog/{version}` - Détail d'une version spécifique
- **Nouveau** : Fichier `docs/API.md` - Documentation complète de l'API

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `backend/routes/docs.py` | Nouveau routeur pour les endpoints de documentation |
| `backend/main.py` | Inclusion du routeur docs |
| `docs/API.md` | Documentation API complète |
| `CHANGELOG.md` | Nouveau fichier de changelog |

### 📋 Checklist pour agents IA

- [ ] Utiliser `/api/docs/changelog/versions` pour lister les versions
- [ ] Consulter `/api/docs/changelog/{version}` pour les détails d'une version

---

## [1.4.0] - 3 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Communication M2M renforcée
- **Amélioration** : Meilleure gestion des tokens M2M avec le Hub
- **Nouveau** : Endpoint `GET /api/m2m/status` pour vérifier la connexion M2M
- **Nouveau** : Endpoint `POST /api/m2m/test-call` pour tester les appels inter-services

### 🔧 Modifications code

| Fichier | Modification |
|---------|--------------|
| `backend/hub_client.py` | Gestion améliorée du cache de tokens |
| `backend/main.py` | Ajout endpoints M2M |

### 📋 Checklist pour agents IA

- [ ] Vérifier le statut M2M avec `/api/m2m/status`
- [ ] Utiliser le token M2M pour les appels inter-services

---

## [1.3.0] - 2 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Gestion des préférences utilisateur
- **Nouveau** : Endpoint `GET /api/preferences` pour récupérer les préférences
- **Nouveau** : Endpoint `PUT /api/preferences` pour mettre à jour les préférences
- **Nouveau** : Modèle `UserPreference` en base de données

### 📝 Modifications

| Fichier | Modification |
|---------|--------------|
| `backend/models.py` | Ajout modèle UserPreference |
| `backend/schemas.py` | Schémas Pydantic pour les préférences |
| `backend/main.py` | Endpoints préférences |

### 📋 Options de préférences

| Préférence | Type | Valeurs | Défaut |
|------------|------|---------|--------|
| `theme` | string | light, dark, system | system |
| `language` | string | Code langue (2-5 car.) | fr |
| `items_per_page` | int | 5-100 | 20 |
| `email_notifications` | bool | true/false | true |

---

## [1.2.0] - 2 janvier 2026

### ✨ Nouvelles fonctionnalités

#### CRUD Items complet
- **Nouveau** : `GET /api/items` - Liste paginée des items
- **Nouveau** : `POST /api/items` - Création d'item
- **Nouveau** : `GET /api/items/{id}` - Lecture d'un item
- **Nouveau** : `PUT /api/items/{id}` - Modification d'un item
- **Nouveau** : `DELETE /api/items/{id}` - Suppression d'un item

### 🔧 Modifications code

| Fichier | Modification |
|---------|--------------|
| `backend/models.py` | Modèle Item avec owner et timestamps |
| `backend/schemas.py` | Schémas ItemCreate, ItemUpdate, ItemResponse |
| `backend/main.py` | Endpoints CRUD avec pagination |

### 📋 Règles d'accès aux items

| Authentification | Accès |
|------------------|-------|
| Aucune | Items publics uniquement |
| User | Items publics + ses propres items |
| Admin | Tous les items |

---

## [1.1.0] - 1 janvier 2026

### ✨ Nouvelles fonctionnalités

#### Système de rôles hiérarchiques
- **Nouveau** : Hiérarchie des rôles : `admin > manager > user > viewer`
- **Nouveau** : Endpoints protégés par rôle
- **Nouveau** : Support des Service Accounts

### 📝 Endpoints par rôle

| Endpoint | Rôles autorisés |
|----------|-----------------|
| `/api/viewer-only` | viewer, user, manager, admin |
| `/api/user-only` | user, manager, admin |
| `/api/manager-only` | manager, admin |
| `/api/admin-only` | admin |
| `/api/service-only` | Service Accounts uniquement |

### 🔧 Modifications code

| Fichier | Modification |
|---------|--------------|
| `backend/hub_auth.py` | Décorateurs require_role, require_any_role |
| `backend/hub_auth.py` | Fonction require_service_account |
| `backend/main.py` | Endpoints protégés par rôle |

---

## [1.0.0] - 1 janvier 2026

### 🎉 Version initiale

#### Structure du projet
- **Backend** : API FastAPI avec authentification Hub
- **Frontend** : Interface HTML/JS simple avec gestion des tokens
- **Docker** : Configuration Docker Compose pour déploiement

### 📁 Fichiers créés

| Fichier | Description |
|---------|-------------|
| `backend/main.py` | Application FastAPI principale |
| `backend/config.py` | Configuration centralisée |
| `backend/database.py` | Gestion base de données async |
| `backend/models.py` | Modèles SQLAlchemy |
| `backend/schemas.py` | Schémas Pydantic |
| `backend/hub_auth.py` | Authentification Hub JWT |
| `backend/hub_client.py` | Client Hub pour M2M |
| `frontend/index.html` | Interface utilisateur |
| `frontend/auth.js` | Gestion authentification côté client |
| `frontend/config.js` | Configuration frontend |

### 🔐 Authentification

- Validation JWT via clé publique du Hub
- Support tokens utilisateur et service account
- Auto-enregistrement auprès du Hub

### 📋 Endpoints de base

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/config` | Configuration publique |
| `GET /api/public` | Endpoint public |
| `GET /api/protected` | Endpoint authentifié |
| `GET /api/me` | Informations utilisateur |

---

## Format du changelog

Chaque entrée contient :

```markdown
## [VERSION] - DATE

### ✨ Nouvelles fonctionnalités
### 📝 Modifications
### 🔧 Modifications code
### 🗄️ Modifications base de données
### 🔒 Sécurité
### 🐛 Corrections
### ⚠️ Breaking changes
### 📋 Checklist pour agents IA
```

---

## Comment utiliser ce changelog

### Via l'API

```bash
# Voir tout le changelog
curl http://localhost:9045/api/docs/changelog

# Liste des versions
curl http://localhost:9045/api/docs/changelog/versions

# Détail d'une version
curl http://localhost:9045/api/docs/changelog/1.5.0
```

### Format des réponses

L'endpoint `/versions` retourne :
```json
{
  "total_versions": 6,
  "latest_version": "1.5.0",
  "versions": [
    {"version": "1.5.0", "date": "3 janvier 2026"},
    ...
  ]
}
```
