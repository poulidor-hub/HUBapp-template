# Configuration HTTPS avec le Hub

Ce document décrit la configuration nécessaire pour que l'application communique avec le Hub en HTTPS.

## Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Prérequis](#prérequis)
- [Configuration](#configuration)
- [Architecture technique](#architecture-technique)
- [Fichiers impliqués](#fichiers-impliqués)
- [Flux de démarrage](#flux-de-démarrage)
- [Dépannage](#dépannage)

---

## Vue d'ensemble

Lorsque le Hub est configuré en HTTPS avec un certificat auto-signé (ou une CA interne), l'application doit :

1. **Recevoir le certificat CA** du Hub (fourni dynamiquement)
2. **Installer le certificat** au niveau système pour que Python/SSL lui fasse confiance
3. **Attendre le certificat** au démarrage si HTTPS est activé mais le certificat pas encore disponible

```
┌─────────────────┐     HTTPS (443)      ┌─────────────────┐
│   Application   │ ◄──────────────────► │      Hub        │
│    (Backend)    │   Certificat CA      │   (API + Auth)  │
└─────────────────┘                      └─────────────────┘
        │
        │ Monte le dossier ./certs
        ▼
┌─────────────────┐
│  ./certs/       │
│  hub-ca.crt     │ ← Fourni par le Hub
└─────────────────┘
```

---

## Prérequis

1. **Hub configuré en HTTPS** avec un certificat valide
2. **Certificat CA du Hub** (`hub-ca.crt`) disponible
3. **Dossier `./certs/`** existant dans le projet

---

## Configuration

### Variables d'environnement

Ajouter ces variables dans le fichier `.env` :

```bash
# === HTTPS / SSL ===
# Activer HTTPS pour communiquer avec le Hub
HUB_HTTPS_ENABLED=true

# Port HTTPS du Hub (443 par défaut)
HUB_HTTPS_PORT=443

# Chemin vers le certificat CA du Hub (dans le conteneur)
HUB_CA_CERT_PATH=/app/certs/hub-ca.crt
```

### Placement du certificat

Le certificat CA doit être placé dans le dossier `./certs/` à la racine du projet :

```
mon-projet/
├── certs/
│   ├── .gitkeep           # Garde le dossier dans Git
│   └── hub-ca.crt         # Certificat CA du Hub (fourni par le Hub)
├── backend/
├── frontend/
├── docker-compose.yml
└── .env
```

> **Note** : Le certificat `hub-ca.crt` est fourni dynamiquement par le Hub et ne doit **pas** être versionné dans Git. Seul `.gitkeep` est versionné.

---

## Architecture technique

### Fichiers impliqués

| Fichier | Rôle |
|---------|------|
| `docker-compose.yml` | Monte le dossier `./certs` dans `/app/certs` |
| `Dockerfile.backend` | Installe `ca-certificates` et configure l'entrypoint |
| `backend/entrypoint.sh` | Installe le certificat au niveau système au démarrage |
| `backend/config.py` | Définit les variables HTTPS et la logique `hub_ssl_verify` |
| `backend/hub_client.py` | Attend le certificat et l'utilise pour les appels HTTPS |

### docker-compose.yml

```yaml
services:
  api:
    environment:
      - HUB_HTTPS_ENABLED=${HUB_HTTPS_ENABLED:-false}
      - HUB_HTTPS_PORT=${HUB_HTTPS_PORT:-443}
      - HUB_CA_CERT_PATH=${HUB_CA_CERT_PATH:-/app/certs/hub-ca.crt}
    volumes:
      # Dossier des certificats (le Hub y dépose hub-ca.crt dynamiquement)
      - ./certs:/app/certs:ro
```

### Dockerfile.backend

```dockerfile
# Dépendances système pour ca-certificates
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Créer le répertoire pour le certificat CA Hub
RUN mkdir -p /app/certs

# Rendre l'entrypoint exécutable
RUN chmod +x /app/entrypoint.sh

# Utiliser l'entrypoint pour installer le certificat CA
ENTRYPOINT ["/app/entrypoint.sh"]
```

### backend/entrypoint.sh

```bash
#!/bin/bash
set -e

CA_CERT_PATH="${HUB_CA_CERT_PATH:-/app/certs/hub-ca.crt}"

if [ "$HUB_HTTPS_ENABLED" = "true" ]; then
    if [ -f "$CA_CERT_PATH" ] && [ -s "$CA_CERT_PATH" ]; then
        echo "🔐 Installation du certificat CA du Hub dans le système..."
        cp "$CA_CERT_PATH" /usr/local/share/ca-certificates/hub-ca.crt
        update-ca-certificates > /dev/null 2>&1
        echo "✅ Certificat CA installé avec succès"
    else
        echo "⚠️ HTTPS activé mais certificat CA non disponible"
        echo "   L'application va attendre le certificat au démarrage..."
    fi
fi

exec uvicorn main:app --host 0.0.0.0 --port 8000
```

### backend/config.py

```python
class Settings(BaseSettings):
    # === HTTPS / SSL ===
    HUB_HTTPS_ENABLED: bool = False
    HUB_HTTPS_PORT: int = 443
    HUB_CA_CERT_PATH: Optional[str] = None
    
    @property
    def hub_api_url(self) -> str:
        """URL complète de l'API Hub (HTTP ou HTTPS)."""
        if self.HUB_HTTPS_ENABLED:
            port = f":{self.HUB_HTTPS_PORT}" if self.HUB_HTTPS_PORT != 443 else ""
            return f"https://{self.hub_host}{port}"
        return f"http://{self.hub_host}:{self.HUB_API_PORT}"
    
    @property
    def hub_ssl_verify(self) -> Union[str, bool]:
        """Certificat CA pour vérifier le Hub en HTTPS."""
        if self.HUB_HTTPS_ENABLED:
            if self.HUB_CA_CERT_PATH:
                ca_path = Path(self.HUB_CA_CERT_PATH)
                if ca_path.exists():
                    return str(ca_path)
            return False  # HTTPS sans CA (⚠️ non sécurisé)
        return True  # HTTP = pas de SSL
    
    def is_hub_certificate_available(self) -> bool:
        """Vérifie si le certificat CA du Hub est disponible."""
        if not self.HUB_HTTPS_ENABLED:
            return True
        if not self.HUB_CA_CERT_PATH:
            return False
        return Path(self.HUB_CA_CERT_PATH).exists()
```

### backend/hub_client.py

```python
# Configuration attente certificat Hub
CERT_WAIT_INTERVAL = 2   # secondes entre chaque vérification
CERT_WAIT_TIMEOUT = 120  # timeout max en secondes (2 minutes)

async def wait_for_hub_certificate(timeout: int = CERT_WAIT_TIMEOUT) -> bool:
    """
    Attend que le certificat CA du Hub soit disponible.
    
    Le certificat est fourni dynamiquement par le Hub et monté via docker-compose.
    Cette fonction bloque le démarrage jusqu'à ce que le certificat soit présent
    ou que le timeout soit atteint.
    """
    settings = get_settings()
    
    if not settings.HUB_HTTPS_ENABLED:
        return True  # Pas besoin d'attendre si HTTPS désactivé
    
    if not settings.HUB_CA_CERT_PATH:
        logger.warning("HUB_CA_CERT_PATH non configuré mais HTTPS activé")
        return False
    
    cert_path = Path(settings.HUB_CA_CERT_PATH)
    elapsed = 0
    
    while elapsed < timeout:
        if cert_path.exists() and cert_path.stat().st_size > 0:
            # Installer au niveau système
            shutil.copy(cert_path, "/usr/local/share/ca-certificates/hub-ca.crt")
            subprocess.run(["update-ca-certificates"], capture_output=True)
            return True
        
        await asyncio.sleep(CERT_WAIT_INTERVAL)
        elapsed += CERT_WAIT_INTERVAL
    
    return False  # Timeout
```

---

## Flux de démarrage

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DÉMARRAGE CONTENEUR                         │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1. entrypoint.sh                                                   │
│     ├── HUB_HTTPS_ENABLED=true ?                                    │
│     │   ├── OUI: Certificat présent ?                               │
│     │   │   ├── OUI: Copie vers /usr/local/share/ca-certificates/  │
│     │   │   │        + update-ca-certificates                       │
│     │   │   └── NON: Log warning, continue                         │
│     │   └── NON: Pas d'action SSL                                  │
│     └── Lance: uvicorn main:app                                    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. main.py - Application startup                                   │
│     └── hub_client.register()                                       │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. hub_client.py - register()                                      │
│     ├── HUB_HTTPS_ENABLED=true ?                                    │
│     │   └── OUI: wait_for_hub_certificate()                        │
│     │       ├── Attend jusqu'à 120s que /app/certs/hub-ca.crt      │
│     │       │   soit présent et non vide                            │
│     │       ├── Installe au niveau système (backup)                │
│     │       └── Retourne True/False                                │
│     └── httpx.AsyncClient(verify=settings.hub_ssl_verify)          │
│         └── POST https://hub/api/apps/register                     │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4. Application prête                                               │
│     └── Tous les appels httpx utilisent hub_ssl_verify             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Dépannage

### Erreur : `CERTIFICATE_VERIFY_FAILED`

```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
```

**Causes possibles :**
1. Le certificat `hub-ca.crt` n'existe pas ou est vide
2. Le certificat n'a pas été installé au niveau système
3. Le certificat est incorrect (ne correspond pas au Hub)

**Solutions :**
```bash
# Vérifier que le certificat existe
ls -la ./certs/hub-ca.crt

# Vérifier le contenu du certificat
cat ./certs/hub-ca.crt | head -5
# Doit afficher: -----BEGIN CERTIFICATE-----

# Vérifier dans le conteneur
docker exec mon-app-api ls -la /app/certs/
docker exec mon-app-api cat /app/certs/hub-ca.crt | head -5

# Vérifier l'installation système
docker exec mon-app-api ls -la /usr/local/share/ca-certificates/
```

### Erreur : Le certificat est un dossier

Si Docker crée un dossier `hub-ca.crt` au lieu de monter le fichier :

```bash
# Supprimer le dossier erroné
sudo rm -rf ./certs/hub-ca.crt

# Vérifier que le fichier source existe
ls -la ./certs/
```

> **Important** : Depuis la dernière mise à jour, on monte le **dossier** `./certs` et non le fichier directement, ce qui évite ce problème.

### Logs de diagnostic

```bash
# Voir les logs de démarrage
docker compose logs api | grep -E "(🔐|✅|⚠️|❌|SSL|certificate|HTTPS)"

# Logs attendus si tout fonctionne :
# 🔐 Installation du certificat CA du Hub dans le système...
# ✅ Certificat CA installé avec succès
# 🚀 Démarrage de l'API...
# ⏳ Attente du certificat CA du Hub: /app/certs/hub-ca.crt
# ✅ Certificat CA du Hub disponible: /app/certs/hub-ca.crt
# HTTP Request: POST https://192.0.2.11/api/apps/register "HTTP/1.1 200 OK"
# ✅ Application 'mon-app' enregistrée au Hub
```

### Mode dégradé (HTTP)

Pour désactiver temporairement HTTPS et revenir en HTTP :

```bash
# Dans .env
HUB_HTTPS_ENABLED=false
HUB_API_PORT=8000
HUB_FRONTEND_PORT=80
```

---

## Checklist de déploiement

- [ ] `HUB_HTTPS_ENABLED=true` dans `.env`
- [ ] `HUB_HTTPS_PORT=443` (port HTTPS du Hub)
- [ ] `HUB_CA_CERT_PATH=/app/certs/hub-ca.crt`
- [ ] Dossier `./certs/` existant avec `.gitkeep`
- [ ] Certificat `hub-ca.crt` présent dans `./certs/` (fourni par le Hub)
- [ ] Volume monté : `./certs:/app/certs:ro` dans `docker-compose.yml`
- [ ] Image reconstruite après modification du Dockerfile

---

## Résumé des modifications (commit 86d7426)

| Fichier | Modification |
|---------|--------------|
| `Dockerfile.backend` | Ajout `ca-certificates`, `ENTRYPOINT` vers `entrypoint.sh` |
| `backend/entrypoint.sh` | Nouveau script d'installation du certificat au démarrage |
| `backend/config.py` | Variables `HUB_HTTPS_*`, propriétés `hub_ssl_verify`, `is_hub_certificate_available` |
| `backend/hub_client.py` | Fonction `wait_for_hub_certificate()` avec installation système |
| `docker-compose.yml` | Variables d'environnement HTTPS, volume `./certs:/app/certs:ro` |
| `certs/.gitkeep` | Garde le dossier dans Git |
