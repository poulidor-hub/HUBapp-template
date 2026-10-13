## [2.30.2] - 13 octobre 2026

### ⚡ allocate_ports : repli localhost pour l'allocation des ports (CAS 1)

- **Fix** : l'endpoint Hub `POST /api/apps/allocate-ports` n'accepte que des
  IP **réseaux Docker** (whitelist anti-abus 172.17–31). Depuis l'hôte via
  `HUB_HOST=<IP LAN>`, la source vue par `hub-api` est hors whitelist →
  `HTTP 403` → `make sync-env` échouait sur un `.env` frais (premier boot),
  et le fallback legacy allouait un subnet `10.220.x` (plage exemple-app)
  inadapté au parc avant de sortir en erreur.
- Désormais : quand `APP_HOST` est vide (app sur le même serveur que le Hub),
  nouvel essai via `http://localhost:{port}` — la source devient la gateway
  Docker → accepté, valeurs du parc obtenues (ex. `10.50.x.0/24`). Le fallback
  legacy reste le dernier recours ; en app distante (`APP_HOST` renseigné),
  comportement inchangé (pas de repli localhost).
- **Tests** : `ACTIONS/PYTHON/test_allocate_ports.py` (4 cas — repli
  403→localhost sans fallback legacy, pas d'appel superflu, pas de repli en
  remote, skip si déjà alloué) ; suite ACTIONS complète 36 passed.
- Détecté via l'app exemple-app (même bug sur sa copie, corrigé en 0.8.2).

---

## [2.30.1] - 8 octobre 2026

### ⚡ docs(front) — directive IA sèche + skills resynchronisés

- **`frontend/README.md`** : la matrice de consommation (seed / vendor /
  Verdaccio) remplacée par la directive — « classes `hub-*` du seed, c'est
  tout » ; recette + 4 règles + mapping conservés ; option React DS résumée
  à un renvoi vers `HUBCSS/docs/HOW2USE.md`.
- **Skills frontend resynchronisés** : `frontend-crud-page` (directive
  « UI Directive — read first » : structure canonique + 4 règles + référence
  ExampleList), `react-list-rendering`, `badge-search-system`,
  `bulk-operations` — références `DataTable.jsx` (supprimé en 2.30.0)
  → `ExampleList.jsx`.
## [2.30.0] - 8 octobre 2026

### ⚡ Phase 2 — template exemplaire CSS-first (structure canonique, purge app.css, seed HUBCSS 0.3.0)

- **Structure canonique** : `components/PageHeader.jsx` (markup
  `hub-page-header` du DS 0.3.0 — title/back/badge/version défaut
  APP_VERSION/meta/actions) ; routes réécrites (`index`, `demo/form`,
  `notFound`) en composition visible `PageHeader > toolbar unique >
  hub-panel` ; `components/ExampleList.jsx` remplace le monolithe
  `DataTable.jsx` (410 l., dead code — importé nulle part).
- **Purge app.css** : `.btn*/.card*/.role-badge*/.empty-state*/.category-badge`
  + alias `--bg-*` supprimés ; 8 composants socle migrés `hub-*` (LoginPrompt,
  TokenCard, UserCard, M2MTests, EndpointTests, FormDemo, Header,
  ErrorBoundary) ; style socle titres de panels (`.hub-panel > h2:first-child`).
- **Seed HUBCSS 0.3.0** (`make refresh-design-seed`) : classes structurelles
  livrées d'office (`hub-page-header*`, `hub-modal*`, `hub-panel--padded`,
  tokens z-index).
- **INITIALISE** : rebranding Header bruyant (échec explicite si motif absent,
  `update_file` global) + regex robuste (h1 multiligne, span imbriqué, icône
  préservée) — fin des rebrandings silencieusement ratés.
- **frontend/README.md** : recette de page canonique + 4 règles + matrice de
  consommation HUBCSS (seed CSS / paquet React vendor / Verdaccio) + gotcha
  `up -V`.
- Exécuté en subagent-driven (6 tâches reviewées + review finale + e2e app
  fraîche : Header rebrandé + structure canonique héritée d'emblée).
## [2.29.5] - 8 octobre 2026

### ⚡ fix(front) — TDZ « logout » dans AuthContext : crash des apps neuves au premier render

- **`frontend/src/context/AuthContext.jsx`** : le `useEffect` de
  décodage/expiration du token référençait `logout` dans son tableau de deps
  **avant** sa définition (`const logout = useCallback(...)` plus bas) —
  TDZ « Cannot access 'logout' before initialization » à chaque render, donc
  crash total de l'AuthProvider sur toute app fraîchement créée depuis le
  template. Régression introduite par `05a2aff` (sync inter-onglets) :
  invisible jusqu'ici, les apps existantes ayant été créées avant.
- Fix : le `useEffect` est déplacé **après** la définition de `logout`
  (comportement inchangé, ordre de déclaration corrigé).
- Détecté par le test e2e `lab-hubcss` (création d'une app depuis le template
  pour valider HUBCSS 0.3.0) ; fix validé en conditions réelles sur cette app
  + build frontend vert.
## [2.29.4] - 5 octobre 2026

### ⚡ fix(hub) — plugin opencode hub.ts migré au format API V2

- `.opencode/plugins/hub.ts` resynchronisé depuis le méta-repo (0.70.7) :
  export par défaut `{ id: "hub.guard", setup }` + hook
  `ctx.permission.hook("evaluate")` — le superviseur de plugins OpenCode v2
  (binaire embarqué OpenChamber v2.0.22) rejette l'ancien format V1.
- Garde-fou « opérations destructrices » (rétrogradation allow→ask) de nouveau
  actif dans toutes les sessions ; sémantique inchangée.


## [2.29.3] - 4 octobre 2026

### ⚡ Logging horodaté à l'heure du Hub

- **`backend/logging_config.py`** (nouveau) : `setup_logging()` configure
  root + loggers uvicorn avec le format parc
  `2026-10-04T12:34:56.789Z | LEVEL | logger | message` (ISO 8601 UTC,
  règle parc n°10). `HubClock` maintient l'offset (heure hub − heure
  locale) ; `HubTimeFormatter` horodate chaque record. Niveau via
  `LOG_LEVEL` (défaut INFO). Idempotent.
- **`hub_client.sync_hub_time()`** : synchro via `GET /api/system/time`
  (`epoch_ms`, public) au point médian request/réponse ; appelée au boot
  après register, puis périodiquement par la boucle de fond
  `hub_time_sync_loop` (`HUB_TIME_SYNC_INTERVAL`, défaut 300 s, tâche
  annulée au shutdown). Échec → dernier offset conservé (fallback heure
  locale UTC) ; hub sans `epoch_ms` → rejet explicite.
- **`main.py`** : `basicConfig` remplacé par `setup_logging()` (fin de
  l'heure conteneur non synchronisée) ; sync immédiate en lifespan.
- **Config** : `HUB_TIME_SYNC_INTERVAL` (Settings + `.env.example`,
  avec `LOG_LEVEL`).
- **Tests** : `tests/test_logging_config.py` (13 tests — offset, format,
  setup, sync mockée, fallback). Suite complète : 266 passed.

## [2.29.2] - 4 octobre 2026

### ⚡ Plugins OpenCode V2 — superpowers réparé + hub.ts migré

- `opencode.json` : clé `plugin` renommée `plugins` (format canonique V2) et
  pin superpowers déplacé de `896224c` (v6.0.3, format plugin V1 seul, rejeté
  au chargement par l'API plugin V2) vers `8ca22db` (tag v6.4.2,
  dual-compatible V1/V2). Les skills superpowers (brainstorming,
  test-driven-development, systematic-debugging,
  verification-before-completion, using-git-worktrees…) se chargent à
  nouveau.
- `.opencode/plugins/hub.ts` : migration au format plugin V2 — export
  `default { id: "poulidor-hub", setup(ctx) }` (l'ancienne fonction V1
  déclenchait `Plugin must export a default definition…`) et hook
  `permission.ask` remplacé par `ctx.permission.hook("evaluate", …)`.
  Garde-fou inchangé : toute décision `allow` matchant un motif destructeur
  (`hub_*_delete`, `rm -rf`, `docker compose down -v`, `git push --force`,
  `prod… deploy`…) est rétrogradée `ask`.
- Validé en runtime : les deux plugins se chargent sans erreur sous l'API
  plugin V2 (logs serveur OpenCode). Copie template synchronisée avec la
  source de vérité POULIDOR.

## [2.29.0] - 1er octobre 2026

### ⚡ Nouveau skill socle — data-generate (données de test sans données réelles)

- `.opencode/skills/data-generate/SKILL.md` : règle de parc invariante —
  jamais de données réelles (prod, exports clients) en dev/test. Voie A :
  données synthétiques (appels CRUD ≤ ~50 items, script one-shot seedé
  au-delà, domaines `@example.*`). Voie B (réalisme dérivé du réel) :
  anonymisation exemple-app obligatoire AVANT tout usage — upload
  (CSV/XLSX/ODS) → MaskConfig fake/stat → job `anonymize` seedé
  (`effective_seed`) → `GET /api/jobs/{id}/download` → `validate`
  (`global_score`) → destruction de l'export source.
- Table de réfutation des rationalisations (testée baseline subagents
  RED/GREEN/REFACTOR selon writing-skills) + red flags (sunk cost,
  « juste pour la démo », pseudo-anonymisation artisanale) + hygiène
  (seed enregistré, nettoyage post-test, jamais de réel dans git /
  `/tmp` / `uploads/`, jamais la DB de prod).
- `.opencode/agent/jellycode.md` : `data-generate` ajouté à la liste des
  skills app.
- Dérivés de données réelles : agrégats statistiques autorisés, « variantes »
  de vrais dossiers interdites (ré-identifiables).

---

## [2.29.1] - 3 octobre 2026

### ⚡ sync_hub_host : fallback IP LAN si annonce injoignable et HUB_HOST vide/mort

- Complément du garde dfc672d (conservé tel quel, cas « HUB_HOST courant joignable ») : quand le courant est **vide ou mort**, l'annonce du Hub était adoptée **sans validation** — une IP injoignable (config Hub obsolète après changement d'IP de la machine, IP de conteneur annoncée par auto-détection inter-bridges) finissait dans le `.env` et l'app perdait le Hub au prochain build
- Incident réel 01/10/2026 (app instanciée) : `HUB_HOST=10.50.150.133` propagé par le sync → `hub_connected` perdu à la recréation des conteneurs
- Désormais, si l'annonce ne répond pas depuis l'hôte : adoption de l'IP LAN (`get_local_ip`, port du Hub publié sur 0.0.0.0) si le Hub y répond ; sinon **aucune écriture** + avertissement
- Tests : 4 cas unitaires (`test_sync_hub_host.py` — courant joignable conservé, fallback LAN, adoption normale inchangée, tout-mort sans écriture)

## [2.29.0]
## [2.28.3] - 29 septembre 2026

### ⚡ Fix socle — réparation automatique des permissions de volumes au démarrage

- `backend/entrypoint.sh` + `Dockerfile.backend` : l'entrypoint démarre en
  root, corrige la propriété (`chown -R 1000:1000`) des répertoires de
  données montés en volume (`/app/storage`, `/app/uploads`, `/app/certs`,
  `/app/data`, `/app/DATA`) puis abaisse les privilèges via `gosu` :
  **l'application tourne toujours en non-root** (durcissement préservé,
  pattern images officielles postgres/redis).
- `docker-compose.yml` (service api) : ajout des caps `CHOWN`, `SETUID`,
  `SETGID` — strictement nécessaires à la séquence chown→gosu avec
  `cap_drop: ALL`. `no-new-privileges` conservé.
- Motivation (incident prod réel, app exemple-app site distant) : volumes créés
  par root (ancien conteneur root / exécution sudo) → l'app non-root ne
  pouvait plus écrire (SQLite `readonly database`, locks Hub, cache JWKS)
  → 500 sur toute écriture + app jamais enregistrée au Hub. Un simple
  redémarrage du conteneur répare désormais tout, sur tous les sites.
- Vérifié : volume root-owned auto-créé par le daemon → chown auto → app
  opérationnelle, process applicatif en uid 1000.
- `gosu` ajouté aux dépendances runtime Debian.

## [2.28.2] - 24 septembre 2026

### ⚡ Doc skill hub-notifications : durée JWT alignée sur 8h

- **Doc** : le skill app `hub-notifications` annonçait un JWT de 15 min (historique) ;
  le TTL réel est de 480 min = 8h (`ACCESS_TOKEN_EXPIRE_MINUTES=480`, défaut déploiement
  LAN). Le mécanisme de refresh proactif 2 min avant expiration reste inchangé
  (`AuthContext.jsx`).

## [2.28.1] - 23 septembre 2026

### ⚡ sync_hub_host : garde compat hub legacy sur HUB_HOST

- **Fix** : le hub legacy hub-legacy (3.9.x) annonce dans
  `GET /api/config/hub-host` l'IP docker **interne** de son conteneur
  (ex. 172.26.0.3), injoignable depuis le réseau dédié de l'app —
  `make sync-env`/`make up` écrasaient `HUB_HOST` par cette IP morte à
  chaque boot (register M2M en timeout, app en mode dégradé). Désormais :
  si le Hub répond déjà via le `HUB_HOST` courant, il est **conservé** et
  l'annonce ignorée (message explicite, même en `--quiet`). Premier boot
  (`HUB_HOST` vide) et hub injoignable sur l'IP courante : comportement
  inchangé.
- **Tests** : garde legacy (quiet + interactif), cas déménagement précisé
  (ancienne IP morte). 32 (sync_hub_host) + 86 (ACTIONS) verts.

Découvert par le pilote `test-socle-228` sur le banc exemple-app.

## [2.28.0] - 23 septembre 2026

### ⚡ Sous-réseau exemple-app : script manuel + fallback `sync-env` (hub legacy sans allocate-ports)

Le Hub legacy hub-legacy (3.9.x, pré-H9) n'expose pas `POST /api/apps/allocate-ports` :
`make sync-env` échouait bloquant et `docker compose up` refusait de démarrer
(`${APP_SUBNET:?}`). Deux apports pour déployer les apps socle sur exemple-app
pendant la période pré-migration :

- **Ajouté** : `scripts/set_app_subnet.py` — écriture MANUELLE de `APP_SUBNET`
  dans le `.env` existant. Plage dédiée exemple-app `10.220.0.0/16` (un /24 par
  app, disjointe de 10.50/16 hub neuf, 10.210.x ateliers, plages prod
  usuelles). `--subnet CIDR` imposé, sinon auto (premier /24 libre) ;
  `--check` diagnostic sans écriture ; `--force` écrasement explicite.
  Sécurités : refus d'écraser une valeur non vide sans `--force`, disjonction
  vérifiée contre les réseaux Docker actifs + `APP_SUBNET` des `.env` voisins
  (apps éteintes), backup horodaté `.env.pre-subnet-<stamp>`, best-effort si
  Docker indisponible.
- **Ajouté** : `ACTIONS/PYTHON/allocate_ports.py` — fallback local automatique :
  ports déjà figés + subnet vide → allocation locale sans appel Hub ; Hub
  404/injoignable → fallback tenté (les ports manquants restent l'erreur
  bloquante) ; réponse Hub sans champ subnet → même fallback. Logique partagée
  par import de `scripts/set_app_subnet.py` ; Hub neuf inchangé.
- **Tests** : `scripts/test_set_app_subnet.py` (12 cas autonomes) +
  `ACTIONS/PYTHON/tests/test_allocate_ports.py` (11 cas hermétiques).
  Smoke test réel banc (75+ subnets Docker actifs) : allocation disjointe et
  idempotence vérifiées.

## [2.27.1] - 22 septembre 2026

### ⚡ Suite d'audit — backup streaming (RAM bornée) + JWKS hors boucle + skills async

**Backup (routes/backup.py) — le commentaire « RAM bornée » mentait pour la
partie DB : toutes les tables étaient fetchallées en RAM puis le dump complet
sérialisé en une seule string (json.dumps = dict + string en mémoire) — le
bug OOM 512M pouvait récidiver.**

- **Fix** : export — data.json écrit sur DISQUE table par table, lignes par
  batchs (`_iter_table_rows` : `db.stream` + `yield_per` — curseur serveur
  sur asyncpg) ; `_build_backup_zip_sync` reçoit un chemin et copie le JSON
  par chunks ; `table_stats` via `COUNT(*)` ; chemins des fichiers par
  requête légère dédiée. Format `{metadata, data}` inchangé — contrat
  préservé avec les backups existants.
- **Fix** : restore — l'upload entier n'est plus chargé en RAM (BytesIO) :
  copie par chunks de 8 Mo vers un fichier temporaire, `ZipFile` ouvert
  depuis le disque, cleanup garanti en finally. Limite documentée :
  data.json reste lu en RAM une fois.
- +8 tests (`tests/test_backup_streaming.py`).

**Auth (hub_auth.py) — PyJWKClient (urllib synchrone) était appelé dans des
coroutines : initialize(), refresh_jwks_cache() et surtout
_decode_with_jwks() sur CHAQUE requête (via get_current_user) → Hub lent ou
coupé (rotation de clé, kid inconnu) = event loop entièrement gelée, health
checks compris.**

- **Fix** : initialize()/refresh_jwks_cache() — fetch via
  `asyncio.to_thread` (+ verrou anti-stampede sur le refresh).
- **Fix** : decode_token() ne fait JAMAIS de réseau — cache local
  `{kid: PEM}` alimenté par les fetchs async ; kid inconnu →
  `JWKSKeyUnknownError` (cascade PEM conservée, reprise async armée).
- **Fix** : get_current_user/get_optional_user — refresh hors boucle + retry
  unique (`_decode_token_resilient`) → 401 propre en cas d'échec.
- +5 tests (`tests/test_hub_auth_async.py`).

**Skills**

- **Fix** : snippets backend des skills `badge-search-system` et
  `bulk-operations` réécrits en SQLAlchemy 2.0 async conforme à la norme
  `backend/routes/items.py` (`AsyncSession`, `await db.execute`,
  `.scalars()`, `update()` bulk) — les apps dérivées ne copient plus du code
  synchrone qui casse au premier run.
- **Hygiène** : cache JWKS runtime (`backend/storage/`) gitigné — un test
  pouvait laisser un artefact dans le dépôt.

+13 tests au total (249 verts).

---

## [2.28.4] - 1er octobre 2026

### ⚡ Fix UI — header responsive mobile

- `frontend/src/styles/app.css` : media query ≤ 768px sur le `header` — les
  groupes (titre / nav / actions) s'empilent en colonne au lieu de déborder
  horizontalement ; `.header-actions` passe en `flex-wrap` avec `width: 100%`.
  Concerne toutes les apps instanciées (le nav ajouté par certaines apps
  wrappe aussi via `.header-nav` — à compléter côté app si présent).

---


## [2.27.0] - 22 septembre 2026

### ⚡ Audit complet du socle — P0 bloquants, P1 sécurité/fiabilité, P2 cohérence, P3 hygiène

Release issue d'un audit bout-en-bout du template (backend, frontend, infra,
scripts, outillage embarqué). +36 tests (200 → 236), tous les fixes en TDD
(test rouge prouvé avant correction).

**P0 — bloquants**

- **Fix** : `make dev` inopérant — l'overlay dev concaténait les listes
  `ports` au lieu de les remplacer → double bind du port hôte
  (`port is already allocated`). `ports: !override` dans
  `docker-compose.dev.yml` ; en dev, vite (3000) sert le frontend sur le
  même port hôte que nginx (80) en prod.
- **Fix** : les 3 endpoints `/api/hub/data/*` (tables/columns/values)
  renvoyaient 500 systématiquement — `async with get_db()` sur un async
  generator (`TypeError` avant toute logique), zéro test de couverture.
  Injection FastAPI `Depends(get_db)` + `conn.run_sync()` (API async
  correcte) ; `LookupError` au lieu d'une `HTTPException` traversant
  `run_sync`. +9 tests (`tests/test_hub_data.py`).
- **Fix** : `MessageBanner` et `MessageArchive` (messagerie Hub SSE) n'étaient
  montés nulle part — le state `activeMessages`/`unreadMessages` d'AuthContext
  n'avait aucun point de rendu. Câblés dans `RootLayout`
  (`frontend/src/routes/root.jsx`).

**P1 — sécurité & fiabilité (TDD)**

- **Sécurité** : path traversal du storage — `_sanitize_path` laissait
  survivre les segments `..` (écriture hors `UPLOADS_DIR` via owner/category
  d'un ZIP de restore) et `delete_file` n'avait aucun confinement. Sanitize
  neutralisant les points consécutifs, confinement canonique dans
  `_get_file_path` (ValueError), vérification identique à `resolve_path` dans
  `delete_file` ; le restore liste les entrées rejetées sans casser.
  +10 tests (`tests/test_storage_security.py`).
- **Fiabilité** : outbox — un message `in_progress` interrompu par un
  crash/restart était perdu silencieusement (jamais repris). `next_retry_at`
  sert d'horodatage de claim (heartbeat 10 min) : l'`in_progress` dont le
  claim est expiré est repris. `FOR UPDATE SKIP LOCKED` sur le SELECT de
  fetch (2 workers ne prennent plus jamais le même message). Log de purge
  remis avant le `return` (code mort). +5 tests
  (`tests/test_outbox_recovery.py`) ; fixture `outbox_svc` déplacée dans
  conftest.
- **Sécurité** : `require_role` fail-open — `ROLE_MAPPING.get(min_role, 0)`
  rendait le niveau 0 pour une typo (`require_role("admmin")`) → tout
  utilisateur authentifié passait. Désormais `ValueError` à la déclaration
  (crash au boot, typo visible immédiatement). Tests paramétrés sur les 5
  rôles valides.
- **Fiabilité** : migrations SQL — une migration à moitié appliquée
  (statement en échec avalé par savepoint) était quand même marquée
  « appliquée » → jamais re-jouée, sans trace d'erreur fatale. Désormais
  marquée appliquée UNIQUEMENT si tous les statements passent ; sinon log
  ERROR + re-tentative au boot suivant. Split SQL conscient des chaînes
  quotées (`VALUES ('a;b')` ne casse plus). `schema_migrations.applied_at` :
  `DEFAULT CURRENT_TIMESTAMP` (PostgreSQL ET SQLite).
  `apply_migrations(migrations_dir=, engine=)` injectable pour les tests.
  +5 tests (`tests/test_migrations.py`).

**P2 — cohérence vitrine**

- **Fix** : handlers MSW contredisaient le backend (GET /api/items renvoyait
  un array brut `[{id,name,status}]` vs `PaginatedResponse` avec
  `{title,description,is_public}`) — le mock est le contrat d'apprentissage
  du template. Store en mémoire + CRUD items complet + `/api/test-data` +
  validation 422 minimale reflétant les schémas Pydantic.
- **Fix** : `FormDemo` postait vers `/api/items` avec un payload garanti 422
  contre le backend réel → poste désormais vers `/api/test-data` (vrai
  endpoint de démo, `ENABLE_DEMO_ENDPOINTS`).
- **Changement** : route et lien de démonstration `/demo/form` DEV-only —
  404 en production, module tree-shaken du bundle (479 kB vs 548 kB).
- **Docs** : comptage MCP aligné sur le code réel — **77 outils** (le doc
  annonçait 63, le skill ~65, les commandes ~66) ; catalogue complété
  (15 outils manquants dont `hub_pki_*`, `hub_design_*`,
  `hub_backup_export_env`…). `hub.ts` : `hub_app_regenerate_secret`
  rétrogradé « ask » — le garde-fou annoncé par le skill était inexistant.
  API.md : suppression de l'endpoint fantôme `POST /api/m2m/test-call`.
  README : exemple M2M corrigé (`call_discovered_service`).
- **Docs** : skills `badge-search-system` et `bulk-operations` — les
  « sources canoniques » citaient la structure `app/` d'une autre app du
  parc ; réalignées sur les fichiers réels du socle (`backend/routes/`,
  `backend/schemas.py`, `frontend/src/components/DataTable.jsx`, hooks).

**P3 — hygiène**

- **Changement** : Pydantic v2 natif — les 6 `class Config` (dépréciées,
  retirées en v3) migrées vers `model_config = SettingsConfigDict/ConfigDict`.
  Plus aucun DeprecationWarning au boot.
- **Docs** : références obsolètes corrigées (hub-m2m-communication : refs par
  nom de fonction au lieu de numéros de lignes ; verify-feature : liens
  AGENTS.md/instructions réparés ; frontend.instructions.md : `App.jsx` →
  `main.jsx`, `index.css` → `app.css` ; hub-notifications : montage
  RootLayout documenté ; frontend-crud-page : commande inexistante
  reformulée).
- **Ajouté** : ESLint flat config + plugin react-hooks (`npm run lint`) —
  rules-of-hooks en erreur, exhaustive-deps en warning ; 18 imports React
  inutiles supprimés, deps de hooks corrigées (AuthContext : le token sans
  `exp` ne laissait plus d'état semi-auth ; ConfigContext/M2MTests :
  callbacks stabilisés). 0 problème.

**Tests — bug latent de fixtures corrigé**

- **Fix** : `tests/conftest.py` exécutait `create_all` avant tout import de
  `models` → `Base.metadata` vide → aucune table créée pour le premier test
  DB-écrivain de chaque worker xdist (`test_create_item_success` échouait en
  solo). `import models` ajouté — la suite n'est plus ordre-dépendante.

---

## [2.26.4] - 22 septembre 2026

### ⚡ Contexte opencode allégé — MCP hub off par défaut, commandes /hub-on /hub-off

- **Changement** : le serveur MCP `hub` (~66 outils) est **désactivé par défaut**
  dans `opencode.json` — allègement du contexte système (~15-20K tokens/tour,
  time-to-first-token plus rapide), aligné sur le méta-repo POULIDOR 0.66.0.
- **Ajouté** : commandes opencode `/hub-on` et `/hub-off` (`.opencode/command/`)
  pour basculer le MCP à la demande (redémarrage opencode requis) ; fichiers
  identiques au méta-repo (parité de maintenance).
- **Comportement inchangé côté app** : aucune modification backend/frontend ;
  en attendant une activation, les opérations Hub passent par `hubctl`/bash.

## [2.26.3] - 21 septembre 2026

### ⚡ sync-hub-host — le garde-fou d'instance documente la bascule volontaire

- **Amélioré** : message du garde-fou `HUB_INSTANCE_ID` (`sync_hub_host.py`) —
  distingue désormais explicitement l'instance **mémorisée** (ancien Hub) de
  l'instance **détectée** (Hub contacté), et documente la procédure de bascule
  volontaire : corriger `HUB_HOST`, supprimer la ligne `HUB_INSTANCE_ID` du
  `.env`, relancer `make sync-env` (nouvelle instance mémorisée).
  Contexte : retour d'expérience exemple-app — un opérateur restait bloqué sans
  piste lors d'un changement de Hub légitime (fresh install distante).
- **Comportement inchangé** : exit 1, aucune écriture, même déclencheur.
- Tests : garde-fou 30/30 (assertions renforcées sur le message).

---

## [2.26.2] - 20 septembre 2026

### ⚡ Fix hub_client — la version est poussée au hub même avec credentials existants

- Cause racine : `register()` court-circuitait quand `.hub_credentials`
  existait déjà (load + `_sync_state_to_hub` + return) — la version n'était
  envoyée que dans `_do_register()` (première installation). Conséquence :
  après chaque mise à jour d'app, la carte du hub continuait d'afficher
  l'ancienne version enregistrée en base.
- Fix : `.hub_credentials` gagne une 3ᵉ ligne = version de l'app au dernier
  enregistrement effectif (écriture rétrocompatible). `register()` compare
  cette version à `APP_VERSION` : si elle diffère (ou fichier legacy 2 lignes,
  version inconnue) → register complet (`_do_register()`), qui met à jour la
  version côté hub ; sinon, comportement inchangé (sync d'état simple).
- La rotation du secret M2M induite par un ré-enregistrement ne survient donc
  qu'au changement de version — c'est-à-dire précisément lors d'un déploiement.
- Les 4 constructions `HubCredentials` (register, recover, resync legacy,
  regenerate-secret) marquent désormais `version=APP_VERSION` pour éviter
  toute boucle de ré-enregistrement.
- Tests : +4 (`test_hub_client_register_version.py`) ; 2 tests alignés sur le
  nouveau contrat (fichier de fixture avec version courante). 200 verts.

---

## [2.26.1] - 20 septembre 2026

### ⚡ Doc HUB_MCP.md — retrait des 2 outils bootstrap supprimés du MCP

- **hub-mcp 0.4.2** a retiré `hub_auth_create_bootstrap_token` et
  `hub_auth_list_bootstrap_tokens` (fonctionnalité jamais implémentée côté HUB).
- Catalogue doc : **63 outils** (65 → 63, Auth 7 → 5).

## [2.26.0] - 19 septembre 2026

### 🔒 Added / Changed — HTTPS par défaut (HTTPS_ENABLED=true)

- HTTPS activé PAR DÉFAUT (`HTTPS_ENABLED=true`) : docker-compose (api + frontend),
  docker-entrypoint.sh, Settings (`backend/config.py`). Une app qui veut du HTTP
  déclare explicitement `HTTPS_ENABLED=false` dans son `.env`.
- docs/HTTPS.md mis à jour (défaut + note opt-out).
- Spec : docs/superpowers/specs/2026-09-19-https-par-defaut-flotte-design.md (méta).

## [2.25.0] - 19 septembre 2026

### ⚡ Fix — backups volumineux : ZIP en streaming sur disque (fin de l'OOM > 150 Mo)

- **Incident** : la création de backup assemblait le ZIP entièrement en RAM
  (`BytesIO` + `getvalue()` + lecture entière de chaque fichier), soit ~3× la
  taille des données, dans un conteneur limité à 512M → **OOM kernel dès
  ~150 Mo de données** (uvicorn tué, hub : « Server disconnected without
  sending a response », backup failed, rien à télécharger). Reproduit et
  confirmé le 19/09 sur le banc exemple-app exemple-lab (kernel : « Memory cgroup
  out of memory: Killed process (uvicorn) anon-rss:521016kB »).
- **Corrigé** : `create_backup` écrit le ZIP directement sur disque
  (`zipfile.ZipFile(path)` + `zf.write()` streaming, exécuté hors boucle via
  `asyncio.to_thread`) ; checksum en streaming (chunks 1 Mo) ;
  `download_backup` passe en `FileResponse` (streaming disque) au lieu de
  `read_file` + `BytesIO`. RAM proportionnelle au plus gros chunk, plus à la
  taille totale des données.
- **Ajouté** : `StorageManager.resolve_path()` (chemin sûr sans lecture,
  anti-traversée) et `StorageManager.import_file()` (copie + hash par chunks
  de 1 Mo).
- **Déploiement** : `mem_limit` de l'api 512M → **1G** (le JSON des tables
  reste en RAM) ; nginx `client_max_body_size` 50M → **1G** (imports de gros
  backups). Affects les apps à leur prochaine migration/sync template.
- **Tests** : nouvelle classe `TestBackupStreaming` (tracemalloc, fichier
  incompressible de 24 Mo) — échouait sur l'ancienne implémentation
  (pic 81,5 Mo vs seuil 12,6 Mo). Suite : 195 passed. Vérifié en conteneur
  limité à 1G : 300 Mo de données → ZIP 314 Mo, pic RAM python 0,3 Mo.
- Note migration : `mock_storage_manager` délègue désormais à un vrai
  StorageManager (contrat `resolve_path`/`import_file`) — les apps qui
  mockent le storage devront adapter leurs fixtures.

## [2.24.2] - 17 septembre 2026

### 📖 Documentation — README enrichi

- **Ajouté** : bannière + badge de version, section « 🗺️ Place dans le parc » (Mermaid :
  fork INITIALISE, JWT/M2M vers le Hub, design system HUBCSS, migration socle) et
  section « 🛠️ Commandes make » (référence des ~37 cibles du Makefile, dont `test-seq`,
  `verify-ui`, `sync-hub-tooling`).
- **Sync version** : `bump_version.py patch` a rattrapé les fichiers dérivés restés en
  2.23.7 (`frontend/package.json`, `.env.example`, `docs/API.md` → 2.24.2).

## [2.24.1] - 15 septembre 2026

### 🐛 Tests tolérants au slug de l'app instanciée

- **Corrigé** : les mocks de tokens du conftest hardcodaient le slug `"mon-app"` — sur une
  app instanciée avec un autre slug (`settings.APP_SLUG`), `hub_auth` ne résolvait aucun
  rôle → **38 tests en échec** dans `make test-docker`. Les mocks (`create_mock_token`,
  `mock_m2m_token`) et les asserts `test_m2m` utilisent désormais `get_settings().APP_SLUG`.
- Makefile : `test-seq` ajouté à `.PHONY`.
- Validé : 193 passed (hôte slug défaut) ; hôte + conteneur rebuildé avec
  `APP_SLUG=ma-vraie-app` (38 failed → 193 passed). Trouvé par la validation VM du
  chantier outillage (hérité par les apps à leur prochaine migration template).

## [2.24.0] - 15 septembre 2026

### ⚡ Tests parallélisés (pytest-xdist) + cible make test-seq

- **Ajouté** : dépendance `pytest-xdist>=3.6,<4.0` (backend/requirements.txt, installée dans l'image api via wheel build).
- **Ajouté** : `make test` parallèle par défaut (`-n auto`, variable `XDIST_WORKERS`) + nouvelle cible `make test-seq` (séquentiel, debug flaky). `test-cov`, `test-docker`, `test-docker-cov` passent aussi en parallèle.
- Perf : suite template 193 tests, comptes identiques seq/par vérifiés (5.2s — suite courte, gain wall-clock modeste mais mécanique xdist validée hôte et conteneur).
- Skill migrate-app-template (méta) : note propagation « test parallèle par défaut v2.24.0+ » pour les apps migrées.
- Note : la garde `ensure-api-fresh` reconstruit l'image api quand requirements.txt change — `make test-docker` parallèle sans étape manuelle.

## [2.23.7] - 14 septembre 2026

### ✨ HTTPS activé par défaut + fix premier démarrage distant

- **HTTPS par défaut** : `.env.example` passe à `HTTPS_ENABLED=true` — les nouvelles
  installations démarrent en HTTPS : `make up` génère automatiquement les certificats
  auto-signés (`scripts/generate-ssl.sh`, couvre localhost + IP locale) puis charge
  `docker-compose.https.yml` (port HTTPS = FRONTEND_PORT + 1). Les apps existantes ne
  sont pas affectées : la fusion `update_env.py` préserve les valeurs déjà en place.
- **fix `update_env.py` — premier boot serveur distant bloquant** : le script sortait
  en erreur (`exit 1`) dès qu'une variable requise par le compose (`${APP_SUBNET:?}`)
  restait vide, alors qu'au premier démarrage aucun réseau Docker n'existe encore et
  que `allocate_ports.py` (appelé juste après dans `make sync-env`) obtient le subnet
  auprès du Hub (pool `APP_SUBNET_POOL`) — il n'était donc jamais atteint. Ces clés
  (`API_PORT`, `FRONTEND_PORT`, `FRONTEND_HTTPS_PORT`, `APP_SUBNET`) ne sont plus
  fatales dans `update_env.py` : note d'info affichée, allocation déléguée à l'étape
  suivante ; un Hub injoignable reste bloquant via `allocate_ports.py` lui-même.
- **Test** : `scripts/test_update_env.py` — cas 9 (compose exigeant `APP_SUBNET` +
  détecteur réseau `None` → `exit 0`, note d'info, aucune écriture erronée).
## [2.23.6] - 14 septembre 2026

### ✨ Smoke UI par styles calculés (`verify-ui`, item 4)

- **`frontend/scripts/verify-ui.mjs`** : monte dans un vrai Chromium une
  fixture chargant les CSS réellement buildés de l'app (seed HUBCSS + bundle
  `dist/assets`, dans l'ordre d'`index.html`), puis asserte les styles
  calculés de sentinelles à deux viewports (375px / 1280px). C'est la preuve
  runtime que ni un reset hors-layer, ni une classe morte, ni un mapping de
  token n'a cassé le rendu — la classe de bugs invisible à la relecture de
  code (cas exports v0.1.2).
- Config par app : `scripts/verify-ui.config.json` (sentinelles déclaratives :
  sélecteur + propriété + attendu). Usage : `make verify-ui APP=../MON_APP/frontend`.
- Dépendance : `playwright` (devDependency du template) + `npx playwright
  install chromium`. Exit 1 sur échec, 2 sur setup invalide.
- Déployé en réel sur exemple-app (8 sentinelles : sentinelle anti-reset
  `hub-table`, portage thème via `var(--bg-primary)`, `alert-error`,
  `help-text`, utilitaires, `divide-y`, `stat-card`) et exemple-app (6
  sentinelles : anti-reset, `prose`/`prose-sm` du plugin typography,
  Tailwind propre `.p-4`, PrimeIcons bundlé) — **vert mobile + desktop**.

---
## [2.23.5] - 14 septembre 2026

### ⚡ lint-classes — icônes PrimeIcons + utilitaires v4 (vague 5 du parc)

- **Tolérance icônes** : `pi` / `pi-*` (PrimeIcons, CSS importé depuis
  node_modules — invisible du scan seed/src) reconnus comme `bi-*`.
- Utilitaire nu `transition` ajouté ; préfixe `drop-shadow-` ajouté
  (Tailwind v4 propre des apps).
- Campagne réelle : exemple-app (46 classes `pi*`, `prose-*` allowlisté —
  @tailwindcss/typography non installé) et exemple-app (46 `pi*`, 17 hooks
  allowlistés, shell `.app` défini) — **0 classe fantôme**.

---

## [2.23.4] - 14 septembre 2026

### ⚡ lint-classes — heuristique TW élargie (vague 3 du parc)

- Préfixes ajoutés : `file:`, `from-`, `via-`, `to-` (dégradés et variantes
  de formulaire Tailwind).
- Utilitaires nus ajoutés : `group`, `peer`, `transform`, `box-border`,
  `box-content`.
- Faux positifs éliminés en réel sur exemple-app (`.group`), exemple-app
  (6 classes) et exemple-app (`file:*`) — apps avec Tailwind propre.

---

## [2.23.3] - 14 septembre 2026

### ⚡ lint-classes — comparaisons, utilitaires négatifs et fichiers .bak

- **Comparaisons dans `className={…}`** : les chaînes utilisées dans
  `===` / `!==` / comparaisons ne sont plus extraites comme classes
  (ex. `feedback.type === "success"` → `.success` fantôme imaginaire,
  constaté sur exemple-app).
- **Heuristique TW étendue** : utilitaires négatifs (`-mb-px`,
  `-translate-x-full`…), préfixes `table-` / `translate-` — comptés « non
  vérifiables » pour les apps avec Tailwind propre (faux positifs constatés
  sur exemple-app).
- **Fichiers de sauvegarde** (`*.bak`, `*.orig`, `*.rej`) exclus du scan.
- Campagne « vague 1 » du parc : exemple-app, exemple-app,
  exemple-app_v3, exemple-app — **0 classe fantôme** après traitement.

---

## [2.23.2] - 14 septembre 2026

### ⚡ lint-classes — utilitaires Tailwind « nus » + campagne parc (12 apps branches)

- Heuristique `looksLikeTw` étendue : les utilitaires Tailwind sans préfixe ni
  valeur (`border`, `rounded`, `fixed`, `hidden`, `sticky`, `inline-flex`…)
  sont désormais comptés « non vérifiables » pour les apps avec Tailwind
  propre (compilés par leur propre installeur) au lieu d'être des erreurs.
- Script durci pour le traitement en masse du parc : idempotent (reprise
  après interruption), tolère exit 1 du lint (recensement), parsing
  d'expressions `className={…}` à accolades équilibrées.
- Campagne réelle : 12 apps sur branches de travail corrigées (retrait reset
  `*` + lint embarqué) — exemple-app, exemple-app, exemple-V2, exemple-app,
  exemple-app, exemple-app, exemple-app, exemple-app, exemple-app, exemple-app,
  exemple-app, exemple-app.

---

# Changelog - HUBapp Template

Historique des modifications du template d'application Hub.

Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [2.23.1] - 14 septembre 2026

### ⚡ Fix lint-classes — interpolations JSX et apps avec Tailwind propre

- **Faux positif corrigé** : les chaînes situées À L'INTÉRIEUR des
  interpolations `${…}` d'un `className` étaient extraites comme classes
  (ex. `statut-${statut || 'decede'}` → `.decede` fantôme imaginaire, constaté
  sur l'app exemple-app). Le parser extrait maintenant l'expression avec accolades
  équilibrées et ignore tout contenu des interpolations (comptées comme
  dynamiques) ; les fragments tronqués finissant par `-` sont écartés.
- **Apps avec Tailwind propre** (détection de `tailwindcss` dans
  `package.json`) : les classes du dialecte Tailwind non retrouvées dans le
  seed/app.css ne sont plus des erreurs — elles sont comptées comme « non
  vérifiables statiquement » (ℹ️), car compilées par le Tailwind de l'app.
- Validé : faux positif exemple-app disparu, détections réelles inchangées
  (exports 867b5bb : `mb-2`/`mb-3` toujours attrapées ; exemple-app :
  9 classes template manquantes confirmées).

---

## [2.23.0] - 14 septembre 2026

### ✨ Lint anti-classes-fantômes (`make lint-classes`)

Nouveau garde-fou statique qui détecte, **avant le runtime**, les classes
utilisées dans le JSX/HTML mais absentes du build — le mode de défaillance qui
a cassé l'UI de l'app exports (utilitaires Tailwind utilisés après retrait de
Tailwind du build : `mb-2`, `mb-3`… jamais détectés ni par Vite ni par pytest).

- **`frontend/scripts/lint-classes.mjs`** (zéro dépendance, Node seul) :
  - extrait les classes de `className` (chaînes statiques, ternaires, template
    literals hors interpolations) et des attributs `class` du `index.html` ;
  - les compare au seed HUBCSS buildé (`public/design-system/current/global.css`,
    251 classes : composants `hub-*` + utilitaires curatés) et au CSS
    applicatif (`src/**/*.css`) ;
  - **avertit** sur les resets universels `* { … }` hors `@layer` (le piège
    cascade documenté dans `HUBCSS/docs/CASCADE.md`) ;
  - allowlist optionnelle `frontend/scripts/lint-classes.allowlist.json`
    (classes exactes ou regex `/…/`), préfixe `bi-` (bootstrap-icons) toléré ;
  - exit 1 si classe fantôme, 2 si setup invalide (seed manquant → lancez
    `make refresh-design-seed`).
- **Câblage** : script npm `lint:classes`, cible `make lint-classes`,
  intégrée au skill app `verify-feature` (étape frontend) et à sa checklist.
- **Fix détecté par le lint lui-même** : la classe shell `.app` (wrapper de
  `RootLayout`) était utilisée sans définition CSS — règle ajoutée dans
  `app.css` (`min-height: 100vh` + colonne flex, recette `hub-shell`).
- Validé sur : le template (✅ 0 fantôme), l'app exports avant/après fixes
  (l'ancien commit 867b5bb échoue avec `mb-2`/`mb-3` + warning reset — le
  drame Tailwind aurait été attrapé immédiatement), et un cas synthétique
  (allowlist, HTML, dynamique).

---

## [2.22.1] - 14 septembre 2026

### ⚡ Fix UI socle — suppression du reset universel `*` de app.css

Le template livrait `frontend/src/styles/app.css` avec un reset universel
`* { box-sizing: border-box; margin: 0; padding: 0 }` **hors layer**. Or une
règle non-layered bat toujours une règle déclarée dans un `@layer`, quelle que
soit sa spécificité : ce reset écrasait donc silencieusement les paddings et
margins de **tous** les composants HUBCSS (`hub-table`, `hub-button`,
`hub-badge`, `hub-stat-card`, `hub-alert`…) définis dans `@layer components`
du `global.css`. Symptômes en production (cas réel : app exports v0.1.2) :
tableaux écrasés sans padding de cellule, boutons et badges déformés, cartes
stat collées — invisibles à la relecture de code, visibles uniquement dans les
computed styles.

- **Retrait du reset** : le `@layer base` de `global.css` effectue déjà ce
  reset, correctement ordonnancé (layered). Commentaire explicatif laissé à sa
  place, avec renvoi vers `HUBCSS/docs/CASCADE.md`.
- **Doc** : HUBCSS 0.2.3 publie `docs/CASCADE.md` (contrat cascade/layers :
  interdit des resets universels, liste exacte des utilitaires du build,
  patterns sûrs d'extension des `hub-*`).
- Les apps existantes créées depuis ce template portent leur propre copie de
  `app.css` : appliquer le même retrait à la demande (impayé, exports déjà
  corrigées ou immunisées).

---

## [2.22.0] - 13 septembre 2026

### ✨ hub_transfert opt-in + M2M binaire

- **Module `hub_transfert` (opt-in)** : client du service partagé `exemple-app` —
  `upload_file` (push flux + upload chunké au-dessus de 50 Mo), `download_file`
  (streaming), `list_flux`, `transfer_status`, `wait_transfer`. Désactivé par
  défaut (`HUB_TRANSFERT_ENABLED=false`), erreurs `HubTransfertError`/`HubTransfertDisabledError`.
- **`call_discovered_service` : support binaire** — nouveaux paramètres keyword-only
  `timeout` (défaut 30 s, inchangé) et `response_format` (`json`|`bytes`|`stream` —
  le mode `stream` retourne la Response httpx avec corps chargé en mémoire ;
  pour les très gros fichiers, utiliser `hub_transfert.download_file` qui streame
  réellement — défaut `json` = comportement antérieur). Outbox désactivée en modes
  binaires (JSON-only).
- Tests : `tests/test_hub_transfert.py`, `tests/test_hub_client_binary.py`.

## [2.21.2] - 11 septembre 2026

### ⚡ Alignement socle HUBsocle 2.23.2 — vague de fixes banc (AN-3/4/5/7)

Portage dans le template (backend monolithique) des correctifs livrés côté
socle packagé entre v2.21.1 et v2.23.2 (commit `886112d`, campagne de banc du
socle 2026-09-10). Les apps créées avec ce template naissent désormais avec
les mêmes garanties que le socle 2.23.2.

- **Corrigé (AN-3)** : `register()` avec credentials en cache pousse désormais
  l'état is_shared courant au Hub (`PUT /api/apps/me/shared`,
  `_sync_state_to_hub`/`_push_shared_state_to_hub`, best-effort) — changer
  `IS_SHARED` dans le `.env` + redémarrage se propage au Hub. ⚠️ Geste ops :
  le `.env` est lu à la création du conteneur → `docker compose up -d`, pas
  `docker restart`.
- **Corrigé** : deadlock flock en cascade ré-entrante (`get_m2m_token` 403 →
  register dans un register) — flag `_register_in_progress`, chemin ré-entrant
  court-circuité.
- **Corrigé (AN-4)** : `/api/admin/backup/list` triée `created_at` desc ;
  métadonnées relues du `data.json` (`created_by`, `checksum`,
  `includes_files`, `table_stats`) au lieu des placeholders
  `unknown`/`""`/`true`.
- **Corrigé (AN-5)** : `/api/health/detailed` reflète la découverte LIVE des
  services (fallback `app.state.discovered_services_count` si le Hub est
  injoignable).
- **Corrigé (AN-7)** : restore — les erreurs nested par table (lignes
  rejetées) sont agrégées et surfacées dans le top-level `errors`
  (`errors_detail` par ligne).
- **Corrigé (front)** : `formatApiError` (nouveau `hooks/apiError.js`) dans
  `useApiQuery`/`useApiMutation` — les `detail` FastAPI non-string (422 de
  validation) s'affichent en message lisible au lieu de `[object Object]`.
- **Tests** : 8 nouveaux (`tests/test_socle_2232_alignment.py`, adaptés des
  tests HUBsocle 2.23.2) ; suite template : 165 pass.
- **Non porté (hors périmètre template v1)** : INITIALISE v2 / générateur
  d'apps fines et `register_settings_extra` (architecture socle packagé,
  cf. HUBsocle 2.23.x).

---
## [2.21.1] - 7 septembre 2026

### ⚡ Hub legacy : self-healing M2M par regenerate-secret en fallback

- **Contexte** : depuis T2a (2.20.x), `_recover_credentials` ne passait plus
  que par le ré-enregistrement trusted (`POST /api/apps/register`), qui ne
  retourne un `client_secret` que sur les Hubs avec rotation M2M au register
  (≥ ~v3.12). Sur un **Hub legacy** (ex. déploiement exemple, pré-H9), le register
  répond 200 avec `is_new=false` et des credentials **sans secret** → échec
  systématique de la recovery, log « Hub sans correctif T1 ? », app déconnectée
  du Hub après toute perte de credentials (recréation conteneur : `/app/storage`
  non persisté).
- **Fallback legacy** (`_recover_credentials_legacy`) : quand le register ne
  retourne pas de secret, nouvel appel `POST /api/apps/me/regenerate-secret`
  avec `X-Slug` (+ `X-Client-ID` si credentials en cache) — voie self-service
  des Hubs antérieurs, autorisée par whitelist IP réseau Docker, sans token M2M.
  Sur un Hub récent, la voie répond 401 : échec propre, inchangé (la fenêtre
  H9 → rotation sans T1 reste sans issue côté client).
- **Tests** : `TestRecoverCredentialsLegacyHub` (2 cas : recovery OK via
  fallback ; échec 401 → `False`) — cycle TDD, la version sans fallback
  échouait sur le cas nominal. Suite template : 157 passed.

## [2.21.0] - 7 septembre 2026

### ✨ Auth : verrou inter-onglets sur le refresh token + synchronisation d'état

- **Contexte** : les onglets d'une même app partagent le refresh token
  (localStorage). Deux onglets rafraîchissaient en même temps (ex. événement
  SSE `user_permissions_changed` reçu partout à la fois) → le second présentait
  un token déjà consommé → 401 → `logout()` → **onglet fermé**. Complété côté
  Hub par la période de grâce 60 s sur la rotation (HUB_base v3.49.0).
- **Verrou inter-onglets** (`Web Locks API`, nom `hub-token-refresh`) : un seul
  onglet rotate à la fois ; sous le verrou, re-lecture du localStorage — si un
  autre onglet a déjà rotationné, le nouveau token est **adopté sans requête**.
  Fallback sans `navigator.locks` (vieux navigateurs ; note : API limitée aux
  secure contexts — en LAN HTTP pur, la grâce serveur neutralise la course).
- **Sur 401** : re-lecture du localStorage avant `logout()` (l'onglet rival a
  peut-être réussi entre-temps) — la déconnexion devient le dernier recours.
- **Sync inter-onglets** : écoute de l'événement `storage` sur
  `hub_access_token` — quand un onglet met à jour le token, les autres
  adoptent le nouveau sans requête (supprime le « vieux JWT en mémoire »).
- Signature publique inchangée (`refreshAccessToken() → Promise<boolean>`) ;
  aucune animation ajoutée, verrou no-op hors contention ; build Vite vert.

## [2.20.8] - 6 septembre 2026

### 🛠️ Restore : resync séquences robuste (pré-check colonne + savepoint)

- **Correctif du correctif** (validé en conditions réelles sur exemple-app) :
  la resync des séquences appelait `MAX(id)` sur des tables sans colonne
  `id` (ex. `schema_migrations`) → erreur → transaction abortée → le
  `COMMIT` final validait une transaction abortée = **rollback général des
  données importées** (réponse 200 « succès » mensongère).
- **Structure corrigée** : reset de `session_replication_role` AVANT le
  resync (transaction saine), resync isolé par savepoint, pré-check de
  l'existence de la colonne via `information_schema.columns`.
- 155 tests passants.

## [2.20.7] - 6 septembre 2026

### 🛠️ Restore : fix transaction abortée (setval NULL + reset tolérant)

- **Pré-check `pg_get_serial_sequence`** avant `setval` (tables sans colonne
  serial `id` → NULL → transaction abortée → rollback général).
- **Reset `session_replication_role` tolérant** dans le `finally`.
- 155 tests passants.

## [2.20.6] - 6 septembre 2026

### 🛠️ Restore : gestion des cycles de FK + resynchronisation des séquences

- **Cycles de FK** (ex. `groupements ↔ groupement_voicemails`, chacune
  référençant l'autre) : non résolubles par le tri topologique → pendant
  l'import, `SET session_replication_role = replica` désactive les triggers
  FK (rôle superuser requis ; repli gracieux sur l'ordre topologique seul si
  refusé). Remis à `DEFAULT` en `finally` (connexion poolée protégée).
- **Séquences resynchronisées** après import (`setval(pg_get_serial_sequence…,
  MAX(id))`) : l'import insère des ids explicites sans avancer les séquences —
  le prochain INSERT de l'app aurait sinon échoué en duplicate key.
- 155 tests passants.

## [2.20.5] - 6 septembre 2026

### 🛠️ Restore générique : tri topologique des tables + SAVEPOINT par table/ligne

- **Tri topologique** des tables selon les dépendances FK réelles
  (`information_schema` sur PostgreSQL, `PRAGMA foreign_key_list` sur SQLite)
  avant import — corrige l'échec en cascade constaté sur exemple-app
  (`groupements` référençait `groupement_voicemails`, importée en dernier
  dans l'ordre alphabétique → ForeignKeyViolationError → « 12 tables,
  0 importés » renvoyé en 200).
- **SAVEPOINT par table** (`Session.begin_nested`) : une table en échec est
  isolée (rollback au savepoint) et n'empoisonne plus la transaction des
  tables suivantes.
- **SAVEPOINT par ligne** dans `_import_table_data` : une ligne en échec
  (FK, NOT NULL…) est comptée en `errors` sans casser les lignes suivantes.
- **Tests** : `test_backup_restore_order.py` (5 tests — tri topologique pur,
  cycles, auto-références, isolation endpoint).

## [2.20.4] - 3 septembre 2026

### 🧪 Test « démarrage depuis zéro » pour `update_env.py` (10 cas)

- **8a** : `.env` inexistant → le script **refuse proprement** (exit 1, aucun `.env`
  créé, aucun backup) — verrouille la règle du parc « fusion, jamais régénération »
  et le mauvais réflexe `cp .env.example .env` en cours de vie.
- **8b** : flow premier boot sanctionné — `cp .env.example .env` puis `update-env`
  complète les dérivées (`FRONTEND_HTTPS_PORT = FRONTEND_PORT + 1`, `APP_SUBNET`
  via le détecteur réseau), conserve les placeholders INITIALISE, zéro duplication.
- Suite portée à 10 cas, tous verts.
## [2.20.3] - 3 septembre 2026

### 🧪 Test de non-duplication pour `update_env.py`

- Nouveau `scripts/test_update_env.py` : 8 cas autonomes (sans Docker ni pytest,
  `python3 scripts/test_update_env.py`, exit 0/1) verrouillant la fusion B.0 :
  clés existantes avec valeur intouchées (1 occurrence), orphelines préservées,
  clé vide remplacée **en place** (position conservée), clé absente ajoutée
  **une seule fois** (régression du fix 2.20.2), détecteur réseau indisponible
  (pas d'APP_SUBNET fantôme, dérivée hors-Docker conservée), idempotence
  (2ᵉ exécution = no-op, aucun backup), invariant « chaque clé exactement une
  fois après fusion », secrets existants non écrasés.
- Constat à l'écriture des tests : le comportement du script est correct sur
  tous les cas — les 2 attentes initialement fausses (comptage de lignes,
  backup sans écriture) venaient du harnais, pas du fix.
## [2.20.2] - 3 septembre 2026

### 🔧 Corrigé : `update_env.py` perdait silencieusement les clés `filled` absentes du `.env`

- **Bug** : la phase d'écriture utilisait `re.sub` pour poser les valeurs dérivées
  (`FRONTEND_HTTPS_PORT`, `APP_SUBNET`) — si la clé était **absente** du `.env`
  (pas seulement vide, cas exact des vieilles apps ciblées par la migration B.0),
  aucune ligne n'était remplacée et la valeur n'était jamais écrite, alors que le
  rapport annonçait « complété » et « ✅ .env fusionné ».
- **Correctif** : passage à `re.subn` + ajout en fin de fichier quand rien n'a été
  remplacé. Validé sur le cas réel (app sans `APP_SUBNET` : clé désormais écrite,
  valeurs critiques inchangées, backup horodaté créé).
## [2.20.1] — 2 septembre 2026

### 🔧 Skill `app-dependencies` aligné sur le modèle atelier réel

- Retrait des références au modèle atelier fictif (menu « APPS → Atelier »,
  sélection `[→]`, groupe de deps emmené automatiquement, vérification dans
  `APP_Workshop/`, trigger « emmener les deps à l'atelier ») — remplacées par le
  cycle réel `./hubctl atelier X` : sandbox `-ws` à côté de la prod (qui reste en
  place), appels M2M résolus vers les instances prod, pas de groupe à emmener.
- Anti-patterns : retrait de `resolve_group` (n'existe pas dans hubctl) ;
  Quick Reference : retrait de `hubctl_cli/dependencies.py::build_graph()`
  (fichier inexistant). `report_sync` / `depends.yaml` / endpoints Hub (réels)
  inchangés.

## [2.20.0] — 2 septembre 2026

### 🔐 update-env : fusion automatique du `.env` après montée de template

- **Ajouté** : `scripts/update_env.py` + cible `make update-env` — fusionne les nouvelles clés du `.env.example` dans le `.env` existant **sans jamais modifier les valeurs existantes** ni supprimer les clés propres à l'app (orphelines, ex. `HUB_INSTANCE_ID`). Sauvegarde horodatée automatique (`.env.pre-update-<stamp>`), rapport détaillé (ajoutées / conservées / complétées).
- **Variables requises du compose** (syntaxe `${VAR:?...}`, ex. `APP_SUBNET`, `FRONTEND_HTTPS_PORT`) vérifiées après fusion : exit 1 avec message explicite si l'une reste vide. Valeurs dérivées recalculées plutôt que reprises de l'exemple : `FRONTEND_HTTPS_PORT = FRONTEND_PORT + 1`, `APP_SUBNET` lu sur le réseau Docker existant de l'app (déploiements sans Hub ni `make` : `python3 scripts/update_env.py` fonctionne seul).
- **Option `--example CHEMIN`** : pendant une migration, pointer sur le `.env.example` du template (celui de l'app peut encore être ancien).
- **`.gitignore`** : `.env.pre-*` ignoré (les sauvegardes de `.env` contiennent des secrets — ne jamais les committer).
- Contexte : incident réel de déploiement (nouveau compose tiré par git + ancien `.env` → `APP_SUBNET` manquant ; mauvais réflexe `cp .env.example .env` qui casse les identifiants DB). Le skill parc `migrate-app-template` (B.0) s'appuie sur cet outil.

## [2.19.0] — 31 août 2026

### 🔄 sync-env : propagation des ports + garde d'identité du Hub

- **Ajouté** : `make sync-env` propage désormais `HUB_API_PORT`/`HUB_FRONTEND_PORT`
  depuis la réponse `/api/config/hub-host` du Hub (nouvelle réponse enrichie, Hub
  ≥ 3.43.0) et alerte avec la marche à suivre (« recréez les conteneurs ») quand
  un mismatch est corrigé.
- **Ajouté** : garde `HUB_INSTANCE_ID` — l'app mémorise l'identité du Hub au
  premier sync ; si un sync ultérieur contacte une instance différente (mauvais
  port/IP, coexistence), sync-env échoue visiblement (exit 1) SANS écrire, au
  lieu de valider silencieusement le mauvais hub.
- **Comportement** : hub ancien (réponse sans ports/instance) → warning + 
  propagation IP seule, inchangé.
- **Tests** : +5 (première rencontre, mismatch corrigé, mismatch fatal, hub
  ancien, propagation IP préservée) — 25+5 ACTIONS verts.

## [2.18.2] — 31 août 2026

### ⚡ Fiabilité runtime & initialisation (audit ports en dur)

- **Fix certs PKI** : `cert_sync.py` écrivait dans `/ssl` en conteneur (code à
  `/app/`, `parent.parent` = racine fs) au lieu du volume `./ssl:/app/ssl` → le
  renouvellement des certificats HTTPS n'atteignait jamais nginx en prod.
  Nouveau `_get_ssl_dir()` : honore `SSL_DIR` (=`/app/ssl` via docker-compose),
  défaut hôte `<racine>/ssl` inchangé.
- **Fix POSTGRES_PORT** : la variable du `.env` était ignorée (codée en dur
  `5432` dans l'env api). Désormais propagée : `PGPORT` sur le conteneur postgres
  (honoré par le serveur ET les outils clients psql/pg_dump/pg_isready),
  `${POSTGRES_PORT:-5432}` dans l'env api. Portée documentée dans `.env.example`.
- **Fix actions générées** : `START`/`UPDATE` (INITIALISE.py) appelaient
  `docker compose` directement, sans `make sync-env` → échec au premier
  démarrage d'une app initialisée avec ports vides (`APP_SUBNET` requis, ports
  non alloués). Le `_common.py` généré embarque `ensure_env_sync()`
  (sync_hub_host → allocate_ports → `FRONTEND_HTTPS_PORT` = FRONTEND_PORT+1),
  appelé avant tout build/up.
- **Fix depends.yaml** : cherché dans `backend/` (présent dans l'image sous
  `/app`) puis à la racine du projet — avant, le fichier n'existait jamais côté
  conteneur et l'envoi des dépendances au HUB (`_push_deps_to_hub`) était un
  no-op silencieux.
- Tests : +10 nouveaux (résolution SSL_DIR, sync-env des actions générées +
  `_common` généré exécuté, résolution depends.yaml) — 150 backend + 68 ACTIONS
  verts. Audit de la chaîne des ports (.env → compose → backend → frontend/
  nginx) : plus aucun port hôte en dur (seuls les ports internes conteneurs
  restent fixes, jamais exposés).

## [2.18.1] — 30 août 2026

### ⚡ Tolérance aux ports Hub vides (hub legacy)

- **Fix boot** : `HUB_API_PORT`/`HUB_FRONTEND_PORT` vides (variables absentes du
  `.env` sur un hub legacy, substituées en `""` par docker compose) → fallback sur
  les défauts (8000/80) via validator pydantic `empty_port_to_default`, au lieu
  d'un crash uvicorn (ValidationError `int_parsing` au démarrage API)
- `docker-compose.yml` : défauts `${HUB_API_PORT:-8000}` / `${HUB_FRONTEND_PORT:-80}`
- Test `backend/tests/test_config_env.py` : reproduction du bug (rouge sans le fix)

## [2.18.0] — 25 août 2026

### ✨ Persona Jellycode + superpowers (opencode)

- **Ajouté** : persona agent `jellycode` (`.opencode/agent/jellycode.md`).
- **Ajouté** : `default_agent: jellycode` + plugin `superpowers` (pinné) dans `opencode.json`.

---

## [2.17.0] — 23 août 2026

### ✨ Présence utilisateur par app (uptime HUB)

- **Ajouté** : l'URL SSE vers le HUB porte désormais `&app=<slug>` (`config.appSlug`, issu de `VITE_APP_SLUG`). Avec HUB ≥ 3.36.0, le heartbeat SSE (15 s) ouvre/rafraîchit le segment d'usage de l'app côté HUB : l'utilisateur utilisant l'app apparaît dans la page « Uptime utilisateurs » même onglet HUB fermé. Rétro-compatible : le param est ignoré par les HUB plus anciens.

---

## [2.16.0] — 23 août 2026

### ⚡ Garde de fraîcheur d'image pour `make test-docker`

- **Ajouté** : `ACTIONS/PYTHON/check_image_freshness.py` (stdlib uniquement) + `test_check_image_freshness.py` (18 tests) — compare le mtime le plus récent des sources surveillées (`backend/**` caches exclus, `Dockerfile.backend`, `VERSION`) à la date du dernier rebuild assuré. Codes de sortie `0`/`1`/`2` (frais · périmé/absent → rebuild · erreur bloquante).
- **Ajouté** : cible interne `ensure-api-fresh`, prérequis de `test-docker` / `test-docker-cov` — auto-rebuild transparent (`sync-env` → `build api` → `up -d api`) quand l'image est périmée ; respecte le dry-run (`make -n` saute la garde).
- **Mode dev** (`backend` monté dans `/app`) : garde ignorée, le conteneur dev n'est jamais recréé.
- **Stamp `.api-image.stamp`** : posé par `ensure-api-fresh` et `build` après un rebuild réussi, comparé aux sources (repli sur `.Created` de l'image si absent). Corrige la boucle de rebuild infinie quand BuildKit réutilise le cache (`touch` sans changement de contenu → même image ID, même `.Created`, comparaison périmée pour toujours). Ignoré via `.gitignore`.
- **Corrigé (robustesse)** : TOCTOU fs → exit 2 ; `docker inspect` rendant `null` pour les mounts ; message dédié « image introuvable ».
- **Corrigé (build)** : `backend/VERSION` parasite — mountpoint vide créé par le montage `./VERSION:/app/VERSION:ro` du compose dev imbriqué dans `./backend:/app` — entrait dans le contexte de build et `COPY backend/ .` écrasait `/app/VERSION` (crash FastAPI `assert self.version`). Triple défense : `.dockerignore` exclut `backend/VERSION`, `COPY VERSION` déplacé après `COPY backend/`, `.gitignore`.
- Docs : spec + plan d'implémentation (`docs/superpowers/`). Validation end-to-end 4 scénarios (frais / périmé+rebuild / mode dev / cov) — aucun double rebuild, conteneur dev intact.

---

## [2.15.2] — 22 août 2026

### ⚡ Conformité HUBCSS du template (audit complet)

- **Badges de rôle** (`.role-*`) : recette HUBCSS `*-soft` + couleur DS — corrige l'illisibilité en dark mode (10 hex en dur sans variante dark).
- **Badges catégorie** (`.category-*`) : tokens `*-soft` + suppression des 5 overrides `[data-theme="dark"]` manuels (interdits — le dark est géré par les tokens).
- `.data-error` : `danger-soft`/`danger` au lieu de `#ffebee`/`#c62828` + override dark supprimé.
- Tous les `rgba()` en dur remplacés par les tokens `--hub-color-*-soft` ; box-shadows par `--shadow-hub`/`--shadow-hub-raised` ; radius par `--radius-hub{,-sm,-full}` ; `monospace` par `--hub-font-mono` ; typos par `--hub-font-size-*`/`--hub-font-weight-*` (le blanc sur bouton plein reste la recette officielle `.hub-button` du DS).
- **`alert()` éradiqué** : TokenCard → feedback bouton « Copié », FormDemo → résultat inline `.test-result`, AuthContext `force_logout` → banner urgent via MessageBanner (2 s de lecture avant redirection Hub).
- **Emojis UI → Lucide React** (`className="hub-icon"`) : DataTable, TokenCard, UserCard, M2MTests, EndpointTests, MessageArchive, ErrorBoundary.
- **Styles inline → classes** : M2MTests refondu (`.card-intro`, `.card-actions`, `.m2m-*`, `.endpoint-*`, `.service-actions`), FormDemo (`.demo-form-*` + inputs `.data-input`/`.data-select`), ErrorBoundary, liens `.app-link`, utilitaire `.sr-only`.
- `.gitignore` : ignore `.worktrees/` (worktrees agents).
- Vérifs : `npm run build` OK (bundle 21.67 kB CSS), zéro hex/rgba/emoji/alert/inline résiduel.

---

## [2.15.1] — 22 août 2026

### ⚡ Self-healing M2M côté client

- `_recover_credentials()` utilise `POST /api/apps/register` (voie trusted, le Hub fait tourner le secret ou recrée le SA) au lieu de `POST /api/apps/me/regenerate-secret` — voie morte depuis le durcissement H9 (cet endpoint exige un token M2M valide, or le secret est précisément ce qu'on a perdu).
- Payload recover complet, parité avec `_do_register` (inclut `frontend_https_port` : sans lui, le self-healing mid-life d'une app HTTPS écrasait le port HTTPS côté Hub et repassait l'URL en http).
- Cooldown 30 s + `_resync_lock` conservés sur le nouveau chemin ; le secret n'est jamais loggé.

---

## [2.15.0] — 20 août 2026

### 🔄 sync-env — découverte automatique de l'IP du Hub

- **Ajouté** : `make sync-env` découvre et met à jour `HUB_HOST` automatiquement via `GET /api/config/hub-host` du Hub (candidats ordonnés : `HUB_HOST` courant, `localhost`, `127.0.0.1`, IP locale, `host.docker.internal`). Évite l'édition manuelle du `.env` quand le serveur change d'IP.
- **Ajouté** : nouvelle cible `make sync-hub-host` pour gérer explicitement un changement d'IP (découverte auto + prompt interactif de secours, ou `make sync-hub-host HUB_HOST=x.x.x.x` pour forcer / CI / multi-serveur).
- **Ajouté** : script `ACTIONS/PYTHON/sync_hub_host.py` (stdlib uniquement) + tests `ACTIONS/PYTHON/test_sync_hub_host.py`.
- **Ajouté** : bootstrap du `.env` au premier démarrage — `make dev` / `make up` / `make build` créent le `.env` depuis `.env.example` s'il est absent (message `🆕 Premier démarrage`), puis continuent. Le template est désormais démarrable immédiatement après `git clone`, sans édition manuelle.
- **Corrigé** : `sync_hub_host.py` ne crée plus de `.env` partiel en l'absence de `.env` (garde défensive — la création du `.env` reste du ressort du bootstrap Makefile / `INITIALISE.py`).
- **Corrigé** : `.PHONY` du Makefile complété (13→toutes les cibles documentées).
- **Sécurité** : `sync-env` reste non-bloquant — si le Hub est injoignable, il conserve `HUB_HOST` courant en silence (jamais de prompt intempestif sur `make up`).

### 🧪 Stack de développement frontend — MSW, TanStack Router, TanStack Form

- **Ajouté** : MSW (Mock Service Worker) pour développer le frontend sans backend — handlers mockés interceptant les requêtes fetch en mode dev via un Service Worker. Conditionné à `import.meta.env.DEV`, tree-shaké en production.
- **Ajouté** : TanStack Router (routing code-based) remplaçant le mono-page `App.jsx`. Routes : `/` (accueil), `/demo/form` (démo formulaire), `$` (404). Layout dans `routes/root.jsx`.
- **Ajouté** : TanStack Form avec composant démo `FormDemo` (validation SIRET, email, nom) — pattern de référence pour les formulaires d'app.
- **Ajouté** : TanStack React Query DevTools et TanStack Router DevTools, conditionnés à `import.meta.env.DEV`, positionnés à droite et bas-gauche.
- **Corrigé** : `ReactQueryDevtools` désormais conditionné à `import.meta.env.DEV` (précédemment inconditionnel) ; suppression du port redondant dans `docker-compose.dev.yml` (conflit avec le port de base) ; `Dockerfile.frontend.dev` expose le port 80 (au lieu de 3000) pour correspondre au mapping du docker-compose de base.
- **Packages** : deps `@tanstack/react-router` ^1.170, `@tanstack/react-form` ^1.33 ; devDeps `@tanstack/react-router-devtools` ^1.167, `@tanstack/react-form-devtools` ^0.2.31, `msw` ^2.15.

### 🧹 Nettoyage de merge

- **Réaligné** : `frontend/package.json` (resté à 2.11.2) et `APP_VERSION` du `.env.example` (resté à 2.11.0) sur la version réelle du template — les releases 2.12→2.14 n'avaient pas propagé ces fichiers dérivés.
- **Corrigé** : les nouveaux fichiers de la branche devtools utilisaient d'anciennes variables CSS inexistantes (`--color-primary`, `--color-text-secondary`, `--color-danger`) → remplacées par les alias actuels (`--accent`, `--text-secondary`, `--error`) dans `routes/index.jsx`, `routes/notFound.jsx`, `demo/FormDemo.jsx`.
- **Régénéré** : `frontend/package-lock.json` à partir du lock de `main` + nouvelles dépendances devtools (jamais de merge manuel du lock).

---

## [2.14.0] — 17 août 2026

### 🆕 INITIALISE.py — flag `--yes` (mode non-interactif)

- **Ajouté** : `python INITIALISE.py --profile client.json --yes` confirme automatiquement le récapitulatif de configuration — le mode profil restait bloqué sur une confirmation finale `(O/n)`, causant `EOFError`/traceback en non-interactif (CI, harness, scripts d'automatisation). Le récapitulatif reste affiché avant confirmation.
- **Amélioré** : stdin fermé **sans** `--yes` → message explicite (« relancez avec --yes ») et annulation propre au lieu d'un traceback.

## [2.13.0] — 16 août 2026

### ⚡ Épinglage du sous-réseau Docker de l'app (allocation par le Hub)

- **Ajouté** : variable `APP_SUBNET` dans `.env.example` — sous-réseau Docker de l'app (CIDR, ex: `10.50.0.0/24`). Laissée vide, elle est allouée automatiquement par le Hub à la première exécution de `make up`/`make build` (pool `APP_SUBNET_POOL`, défaut `10.50.0.0/16` — voir HUB_base v3.32.0).
- **Ajouté** : `ACTIONS/PYTHON/allocate_ports.py` récupère le champ `subnet` de `POST /api/apps/allocate-ports` et l'écrit dans `.env` ; le shortcut « déjà défini » exige désormais ports **et** sous-réseau (remplissage paresseux pour les apps antérieures à la feature).
- **Ajouté** : `docker-compose.yml` — le réseau `app-network` épingle son sous-réseau via IPAM (`${APP_SUBNET:?…}` avec message d'erreur explicite). L'épinglage est obligatoire : le pool Docker par défaut (`172.16/12`) est saturé sur l'hôte et retombe sur `192.168.16.0/20`, en conflit avec le VPN WireGuard du routeur (`192.168.27.0/24`).
- **⚠ Migration** (apps existantes syncées sur ce template) : `APP_SUBNET` manquant fait échouer `docker compose up` avec l'erreur explicite — relancer `make sync-env` (l'allocation est automatique et idempotente par app).

---

## [2.12.0] — 15 août 2026

### ⚡ Re-synchro périodique des certificats HTTPS depuis la PKI du HUB

- **Ajouté** : module `backend/cert_sync.py` — boucle de fond (synchro immédiate au démarrage puis toutes les 6h) qui récupère le certificat émis par la PKI du HUB et réécrit `ssl/` (`server.crt`/`server.key`/`ca.crt`) uniquement si le contenu a changé. No-op par cycle si `HTTPS_ENABLED=false` (vérifié à chaque itération pour réagir au changement de config sans restart).
- **Ajouté** : `hub_client.fetch_app_cert()` — `POST /api/apps/cert/issue` (token M2M) → `{cert, key, ca, san, fingerprint}` ou `None` si le HUB n'a pas émis de certificat.
- **Ajouté** : après réécriture, reload nginx best-effort (`docker exec … nginx -s reload`, utile en dev) ; en prod (pas de socket docker), avertissement « restart du frontend requis » — la rotation du cert du HUB (changement d'IP, rotation de CA) se propage ainsi sans intervention manuelle.
- **Ajouté** : tâche `cert_sync_loop` lancée au startup de `backend/main.py` et annulée au shutdown ; volume `./ssl:/app/ssl` partagé hôte ↔ backend ↔ frontend dans `docker-compose.yml`.
- **Tests** : `test_cert_sync.py` — pas de réécriture à l'identique, mise à jour sur changement, no-op sans HTTPS.

---

## [2.11.2] — 14 août 2026

### ⚡ AuthContext — purge du refresh token périmé au lancement (bug « onglet qui se referme »)

- **Corrigé** : au lancement d'une app depuis le HUB, un access token frais arrive via
  `?access_token=` **sans** `refresh_token` associé. L'ancien refresh token localStorage
  (session précédente) avait été consommé par la rotation du HUB et était révoqué : au
  premier refresh de l'app → 401 → `logout()` → `hub?action=logout` → `window.close()` →
  l'onglet se refermait aussitôt (il fallait recliquer). Depuis la réduction des access
  tokens à 30 min (ex-480), le bug était quasi systématique.
- **Modifié** : `getInitialToken()` purge désormais le refresh token localStorage quand un
  token de lancement arrive sans refresh token associé (périmé par construction).
- **Documenté** : le skill de migration `migrate-app-template` (section D.3.1 + checklist
  G.2) couvre la détection et la vérification de ce bug pour les apps legacy.

---

## [2.11.1] — 14 août 2026

### ⚡ Sécurité — durcissement des conteneurs (audit #21)

- **Modifié** : `docker-compose.yml` — `security_opt: no-new-privileges:true` et
  `cap_drop: ALL` sur les trois services (pattern `HUB_base`) :
  - **postgres** : capabilities minimales restaurées uniquement
    (`CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `SETGID`, `SETUID` — l'image démarre en root
    puis bascule sur l'utilisateur postgres) ;
  - **api** : zéro capability (l'image tourne en `appuser` et écoute sur 8000,
    port non privilégié) ;
  - **frontend** : `cap_add: NET_BIND_SERVICE` seul (bind des ports 80/443).
- **Modifié** : `Dockerfile.frontend` — conteneur frontend **100 % non-root**
  (`USER nginx`, uid 101) : répertoires cache/logs/`conf.d` pré-chownés au build,
  plus aucun besoin de `CAP_CHOWN`/`CAP_DAC_OVERRIDE` au runtime (pattern
  `HUB_base/frontend/Dockerfile`). NB : l'auto-génération de certificats HTTPS
  suppose un montage `./ssl` accessible à l'uid 101 (`make ssl`).
- **Validé** : tests de boot réels sous options durcies — API (uid 1000,
  `/api/health` healthy), frontend (uid 101, HTTP 200) ; variantes compose
  base/https/dev vérifiées via `docker compose config`.
- **Non propagé** aux apps existantes du parc (effectif à la prochaine migration
  template de chaque app).

---

## [2.11.0] — 13 août 2026

### ⚡ Canevas de cahier des charges (100 % métier)

- **Ajouté** : `cahier-des-charges.html` à la racine du template — outil autonome
  (HTML/CSS/JS vanilla, fonctionne en `file://`, sans backend ni build) pour décrire
  le besoin métier d'une nouvelle app en amont du code, à remplir en atelier (dev + métier).
  - **Canevas 100 % métier** : aucune question technique — l'agent Jellycode dérive la
    couche technique (modèle de données, endpoints, permissions, écrans) depuis la
    spécification produite.
  - 10 questions métier : à quoi sert l'app, comment ça se passe aujourd'hui (existant
    + points de douleur), qui sont les utilisateurs, quelles informations sont gérées,
    que font les utilisateurs, quels écrans/parcours, quelles règles, quel processus
    (logigramme Mermaid), avec quels systèmes échanger, quelles exigences & contraintes.
  - Layout hybride (accordéons + sommaire sticky + indicateurs de remplissage).
  - Exports : **Markdown** (cahier des charges livrable), **export/import JSON**
    (round-trip pour guide vivant), **Spécification agent** (manifest JSON métier
    destiné à être ingéré par l'agent Jellycode pour scaffolder l'app).
  - Thème clair/sombre via tokens HUBCSS + Bootstrap Icons ; impression PDF ;
    anti-perte (`beforeunload`).
- **Ajouté** : section README documentant l'outil et son usage en atelier.

## [2.10.0] — 10 août 2026

### ⚡ INITIALISE.py — mode auto par défaut

- **Ajouté** : mode auto — un seul argument positionnel suffit :
  `./INITIALISE.sh "Gestion des Factures"`. Le slug est dérivé automatiquement
  (`gestion-des-factures`), les ports sont laissés vides pour allocation Hub,
  l'IP du Hub est auto-détectée.
- **Ajouté** : flag `--interactive` pour l'ancien comportement interactif.
- **Ajouté** : fonctions `slugify()` (nom → slug avec suppression accents) et
  `detect_host_ip()` (auto-détection IP via socket).
- **Ajouté** : flag `--force-slug <slug>` pour forcer un slug manuel si la
  dérivation automatique échoue.
- **Modifié** : `parse_cli_options()` enrichi avec détection du nom positionnel
  et des flags `--interactive`/`--force-slug`.
- **Modifié** : `collect_app_info()` dispatche désormais vers le mode auto
  quand un nom est fourni, ou vers le mode profil/interactif selon les flags.
- Les modes `--profile` et `--demo`/`--clean` sont inchangés.

## [2.9.0] - 10 août 2026

### ⚡ Affichage version app dans le header

- **Ajouté** : badge `v{APP_VERSION}` dans le header, sous le titre de l'app
- **Ajouté** : classe CSS `.header-title-group` et `.header-version` pour le style du groupe titre+version

## [2.8.0] - 2 août 2026

### 📣 Pour les développeurs

- **Amélioré** : Les skills du template sont nettoyés et consolidés — fusion, scission, allègement. Chaque app copiée hérite de ~650 lignes de skills en moins.
- **Ajouté** : Nouveau skill `bulk-operations` pour les opérations par lot (select-all filtré, bulk update/delete), extrait de `badge-search-system`.
- **Ajouté** : Nouvelle doc `docs/HUB_MCP.md` — catalogue exhaustif des ~65 outils MCP, séparé du skill pour éviter la dérive.
- **Corrigé** : Le skill `app-dependencies` était invisible (front-matter manquant) — corrigé. `release-sync` pointe désormais vers `release-on-main`.

### ⚡ Refactor massif des skills template — fusion, scission, allègement

- **Fusion** : `hub-messages-integration` (rétrofit legacy, inutile dans une app template) absorbé dans `hub-notifications` (annexe rétrofit, +24 lignes). Skill supprimé.
- **Scission** : `badge-search-system` 616→229 lignes (-63%) — code inline → invariants + renvois vers AssetsPage/OrdersPage. Section batch ops → nouveau skill `bulk-operations` (230 lignes).
- **Migration doc** : `hub-mcp-usage` 207→56 lignes — catalogue 65 outils MCP → `docs/HUB_MCP.md` (155 lignes). Mini-skill = permissions SA/standalone + MCP vs code direct.
- **Allègements** : `hub-oidc-manager` 462→387 (doc code coupée), `release-sync` 57→44 (renvoie release-on-main), `create-hub-app` Phase E/F → pointeurs.
- **Corrections** : `app-dependencies` front-matter ajouté (zombie invisible), `jellycode.md` listing skills à jour (+app-dependencies, ~65 outils MCP, cache headers `immutable`).
## [2.7.0] - 23 juillet 2026

### ⚡ Santé — version et uptime dans /api/health basique

- feat: ajout de `version` (APP_VERSION) et `uptime_seconds` au endpoint `/api/health` basique. Auparavant ces champs n'étaient que dans `/api/health/detailed` (imbriqués sous `app.version`), ce qui empêchait le dashboard de santé du Hub de les collecter sans sonde additionnelle. Le contrat basique est désormais aligné sur le standard du parc.

## [2.6.3] - 22 juillet 2026

### 📚 Doc / Tooling — sync outillage Hub (hub-mcp v0.3.0)

- **Skill `hub-mcp-usage`** : réécrit pour refléter le catalogue réel (65 outils). Ajout d'une section « Modèle de permissions : mode app (SA) vs standalone (admin) » expliquant les `403 « réservé aux utilisateurs »` en mode app (token Service Account) et la solution (mode standalone avec `HUB_ADMIN_USERNAME/PASSWORD`, qui obtient un token utilisateur). Badges 🔓/🔒 par outil. Outils retirés documentés (`pki_*`, `design_*`, `admin_info`, `admin_dns_status`, `discovery_proxy`, `backup_export_env`/`import_env`, `user_reset_password`).
- **Plugin `hub.ts`** : retrait de 2 regex destructrices mortes (`hub_pki_revoke`, `hub_user_reset_password`) — ces outils n'existent plus dans le catalogue hub-mcp v0.3.0.
- Synchronisé depuis le méta-repo POULIDOR (plugin) et aligné sur hub-mcp v0.3.0 (skill).

## [2.6.2] - 21 juillet 2026

### 🐛 Fix — INITIALISE.py mode clean cassait le code généré

- **Corrigé** : le mode `--clean` (défaut) produisait une app qui ne démarrait pas, à cause de deux bugs dans la logique de nettoyage :
  - **`ImportError: OutboxMessage`** : `_clean_models()` réécrivait `models.py` avec un contenu codé en dur qui omettait le modèle core `OutboxMessage` (nécessaire à `outbox.py`). Bug latent révélé quand `OutboxMessage` a été ajouté au template sans mise à jour du contenu codé en dur.
  - **`IndentationError` dans `main.py`** : `_clean_main()` retirait `test_data_router` mais laissait le bloc `if settings.ENABLE_DEMO_ENDPOINTS:` orphelin avec une indentation instable.
- **Fix** : `_clean_models()` ne réécrit plus `models.py` en dur — il retire **ciblément** les classes de démo `Item` et `TestData` (regex) et **préserve tout le reste** (`UserPreference`, `UploadedFile`, `OutboxMessage`, et tout modèle core futur). `_clean_main()` retire désormais proprement le bloc `if ENABLE_DEMO_ENDPOINTS:` complet. Le nettoyage devient robuste face à l'évolution du template (plus de désynchronisation possible).
- **Validé** : recréation d'une app canari en mode clean → démarre, s'inscrit au Hub (`register 200 OK`, `hub_connected: true`).

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
