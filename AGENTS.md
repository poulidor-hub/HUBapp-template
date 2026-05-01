# Project Guidelines

## Architecture

- This repository is split between an async FastAPI backend in [backend](backend), a React 18 + Vite frontend in [frontend](frontend), and Docker Compose orchestration in [docker-compose.yml](docker-compose.yml).
- Keep backend concerns separated: ORM models in [backend/models.py](backend/models.py), Pydantic schemas in [backend/schemas.py](backend/schemas.py), route handlers in [backend/routes](backend/routes), auth in [backend/hub_auth.py](backend/hub_auth.py), and Hub integration in [backend/hub_client.py](backend/hub_client.py).
- Frontend state and API integration are centralized in [frontend/src/context](frontend/src/context) and [frontend/src/hooks](frontend/src/hooks); prefer extending those patterns over introducing parallel abstractions.

## Build And Test

- Work from the repository root unless a file-specific tool requires a subdirectory.
- Preferred commands:
  - `make sync-env` after changing `.env`, ports, or `VERSION`
  - `make up`, `make dev`, `make down` for the default Docker workflow
  - `make test` (host, fast SQLite) and `make test-docker` (inside the api container, runtime image) for backend verification
  - `cd frontend && npm run build` when validating frontend-only changes
- Tests run with pytest from [backend/pytest.ini](backend/pytest.ini); the suite uses async fixtures and an in-memory SQLite database.
- **After any non-trivial change**, follow the standardized cycle in [.github/skills/verify-feature/SKILL.md](.github/skills/verify-feature/SKILL.md): rebuild → boot logs → `make test-docker` → API call → runtime logs.

## Conventions

- Reuse existing auth and dependency helpers instead of re-implementing role or token logic. The main entry points are in [backend/hub_auth.py](backend/hub_auth.py) and [backend/database.py](backend/database.py).
- Use [AI_INDEX.md](AI_INDEX.md) to jump to relevant symbols before broad code searches.
- `VERSION` is the source of truth for released version numbers. Synchronization flows through [scripts/bump_version.py](scripts/bump_version.py), [scripts/install-hooks.sh](scripts/install-hooks.sh), and `make sync-env`.
- Two environment details are easy to miss:
  - leaving `APP_HOST` empty means the app falls back through `APP_HOST -> HUB_HOST -> detected local IP`
  - `FRONTEND_HTTPS_PORT` must remain `FRONTEND_PORT + 1`
- The built frontend does not react to runtime env changes; validate Vite-related config changes with a fresh build.

## Reference Docs

- Link to existing docs instead of copying them into code or instructions:
  - [README.md](README.md)
  - [docs/API.md](docs/API.md)
  - [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md)
  - [docs/DATA_FETCHING.md](docs/DATA_FETCHING.md)
  - [docs/HTTPS.md](docs/HTTPS.md)
  - [docs/HUB_MESSAGES.md](docs/HUB_MESSAGES.md)
  - [docs/REMOTE_APPS.md](docs/REMOTE_APPS.md)
