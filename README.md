# HUBapp_TEMPLATE

Template d'application avec authentification Hub pour le développement rapide d'applications connectées.

## 🎯 Fonctionnalités

- ✅ **Auto-enregistrement** auprès du Hub au démarrage
- ✅ **Validation JWT** avec clé publique JWKS
- ✅ **Gestion des rôles** : viewer < user < manager < admin
- ✅ **Communication M2M** (Machine-to-Machine) inter-services
- ✅ **Base de données PostgreSQL** avec SQLAlchemy async
- ✅ **Frontend** vanilla JS pour tester l'authentification
- ✅ **Docker Compose** prêt à l'emploi
- ✅ **Tests automatisés** avec pytest

## 📁 Structure

```
HUBapp_TEMPLATE/
├── backend/
│   ├── main.py           # Application FastAPI
│   ├── config.py         # Configuration avec auto-détection IP
│   ├── hub_client.py     # Client Hub (M2M, enregistrement)
│   ├── hub_auth.py       # Authentification JWT + rôles
│   ├── database.py       # Configuration PostgreSQL
│   ├── models.py         # Modèles SQLAlchemy
│   ├── schemas.py        # Schémas Pydantic
│   ├── requirements.txt  # Dépendances Python
│   └── tests/            # Tests pytest
├── frontend/
│   ├── index.html        # Interface de test
│   ├── config.js         # Configuration frontend
│   └── auth.js           # Module d'authentification
├── docker-compose.yml    # Orchestration Docker
├── Dockerfile.backend    # Image API
├── Dockerfile.frontend   # Image Frontend (nginx)
├── nginx.conf            # Config serveur statique
└── .env.example          # Variables d'environnement
```

## 🚀 Démarrage rapide

### 1. Configuration

```bash
# Copier la configuration
cp .env.example .env

# Éditer les valeurs (surtout APP_SLUG)
nano .env
```

### 2. Lancement avec Docker

```bash
# Démarrer le Hub d'abord (si pas déjà fait)
# cd /path/to/hub && docker-compose up -d

# Démarrer l'application
docker-compose up -d

# Voir les logs
docker-compose logs -f api
```

### 3. Accès

- **Frontend** : http://localhost:4178
- **API Docs** : http://localhost:18087/api/docs
- **Health** : http://localhost:18087/api/health

## 🔐 Endpoints par rôle

| Endpoint | Rôle minimum | Description |
|----------|--------------|-------------|
| `GET /api/public` | - | Accessible sans authentification |
| `GET /api/protected` | token | Token valide requis |
| `GET /api/viewer-only` | viewer | Lecture seule |
| `GET /api/user-only` | user | Lecture/écriture |
| `GET /api/manager-only` | manager | Gestion |
| `GET /api/admin-only` | admin | Administration |
| `GET /api/service-only` | service | M2M uniquement |

## 🧪 Tests

```bash
cd backend

# Installer les dépendances de test
pip install -r requirements.txt

# Lancer les tests
pytest

# Avec couverture
pytest --cov=. --cov-report=html
```

## 🏷️ Gestion des versions

Ce template utilise un **système de versionnage automatique** basé sur [Semantic Versioning](https://semver.org/).

### 🚀 Installation (une seule fois)

Après avoir cloné le template, installez les hooks Git pour activer la synchronisation automatique :

```bash
./scripts/install-hooks.sh
```

C'est tout ! Les versions seront maintenant **synchronisées automatiquement** à chaque commit.

### Fonctionnement automatique

1. **À chaque commit** : Un hook Git synchronise automatiquement les versions dans tous les fichiers
2. **Le développeur n'a rien à faire** : Il suffit de modifier le fichier `VERSION` si besoin
3. **Fichiers auto-synchronisés** : `package.json`, `main.py`, `docs/API.md`

### Changer de version

Pour changer de version, modifiez simplement le fichier `VERSION` :

```bash
# Éditer le fichier VERSION (ex: 1.6.0 -> 1.7.0)
echo "1.7.0" > VERSION

# Au prochain commit, tout sera synchronisé automatiquement !
git add .
git commit -m "feat: nouvelle fonctionnalité"
# -> Les versions sont mises à jour automatiquement
```

### Commandes manuelles (optionnelles)

Si vous préférez utiliser des commandes :

```bash
# Incrémenter automatiquement la version
python3 scripts/bump_version.py patch    # 1.6.0 -> 1.6.1
python3 scripts/bump_version.py minor    # 1.6.0 -> 1.7.0
python3 scripts/bump_version.py major    # 1.6.0 -> 2.0.0

# Vérifier la cohérence
python3 scripts/bump_version.py --check

# Afficher un template de changelog
python3 scripts/bump_version.py --template
```

### Fichiers synchronisés

| Fichier | Élément mis à jour |
|---------|-------------------|
| `VERSION` | Source de vérité |
| `frontend/package.json` | Champ `version` |
| `backend/main.py` | Version FastAPI |
| `docs/API.md` | Badge de version |

### Format du CHANGELOG

Le fichier `CHANGELOG.md` suit le format [Keep a Changelog](https://keepachangelog.com). 
Chaque version doit avoir une entrée avec la structure suivante :

```markdown
## [X.Y.Z] - Date

### ✨ Nouvelles fonctionnalités
- **Nouveau** : Description de la fonctionnalité

### 🐛 Corrections
- **Fix** : Description de la correction

### 📝 Modifications
| Fichier | Modification |
|---------|--------------|
| `fichier.py` | Description du changement |
```

### Endpoint de version

L'API expose un endpoint `/api/version` pour vérifier la version déployée :

```bash
curl http://localhost:9045/api/version
# {"version": "1.6.0", "app": "mon-app", "name": "Mon Application"}
```

## 📝 Personnalisation

### Changer le slug de l'application

1. Modifier `.env` : `APP_SLUG=mon-nouvelle-app`
2. Redémarrer : `docker-compose up -d --build`

### Ajouter un nouveau modèle

1. Créer le modèle dans `backend/models.py`
2. Ajouter les schémas dans `backend/schemas.py`
3. Créer les endpoints dans `backend/main.py`
4. Ajouter les tests dans `backend/tests/`

### Utiliser la communication M2M

```python
from hub_client import hub_client

# Appeler un autre service
result = await hub_client.call_service(
    service_slug="autre-app",
    endpoint="/api/data",
    method="GET"
)
```

## ⚠️ Points importants

1. **Le Hub doit être démarré avant cette application**
2. **Utiliser des IP** (pas `localhost`) pour les URLs
3. **Ne jamais stocker les credentials M2M** dans des fichiers
4. **Les tokens sont gérés par le Hub** - l'app ne fait que les valider

## 📚 Documentation Hub

Pour plus d'informations sur l'intégration :
```bash
curl http://192.0.2.11:8000/api/docs/integration
```
