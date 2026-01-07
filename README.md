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

**Méthode recommandée** (détection automatique du Hub) :

```bash
# Linux/macOS
./start.sh

# Windows (PowerShell)
.\start.ps1
```

Le script détecte automatiquement si le réseau Hub existe et configure l'application en conséquence.

**Commandes disponibles** :

| Commande | Description |
|----------|-------------|
| `./start.sh` ou `./start.sh up` | Démarrer l'application |
| `./start.sh down` | Arrêter l'application |
| `./start.sh restart` | Redémarrer l'application |
| `./start.sh logs` | Afficher les logs (suivis) |
| `./start.sh build` | Reconstruire les images |
| `./start.sh status` | Afficher l'état des services |

**Méthode alternative** (docker-compose direct) :

```bash
# Si le Hub est démarré
docker-compose up -d

# Si le Hub n'est pas démarré, définir les variables
HUB_NETWORK_EXTERNAL=false docker-compose up -d
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

### Endpoints Backup/Restore (admin)

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/admin/backup/estimate` | GET | Estimer taille et durée du backup |
| `/api/admin/backup` | POST | Créer un backup complet |
| `/api/admin/backup/download` | GET | Télécharger le backup (ZIP) |
| `/api/admin/backup/list` | GET | Lister les backups locaux |
| `/api/admin/backup/{id}` | DELETE | Supprimer un backup local |
| `/api/admin/restore` | POST | Restaurer depuis un fichier |
| `/api/admin/sync-to-hub` | POST | Pousser le backup vers le Hub |
| `/api/admin/sync-from-hub` | POST | Restaurer depuis le Hub |

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

## 💾 Système de Backup/Clone

Ce template inclut un système complet de sauvegarde et restauration permettant de cloner intégralement une application.

### Fonctionnalités

- ✅ **Estimation préalable** : Taille et durée estimées avant le backup
- ✅ **Backup complet** : Items, préférences utilisateur, fichiers uploadés
- ✅ **Format ZIP** : `data.json` + dossier `files/` avec tous les fichiers binaires
- ✅ **Synchronisation Hub** : Push/Pull des backups via le Hub central
- ✅ **Restauration sélective** : Choisir quoi restaurer (items, préférences, fichiers)

### Structure du backup

```
backup_{uuid}.zip
├── data.json           # Données structurées (items, préférences, métadonnées fichiers)
└── files/              # Fichiers binaires
    └── {owner}/
        └── {category}/
            └── fichier.pdf
```

### Utilisation

#### 1. Estimer le backup (avant de lancer)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:9045/api/admin/backup/estimate
```

Réponse :
```json
{
  "total_items": 150,
  "total_preferences": 25,
  "total_files": 42,
  "total_size_bytes": 15728640,
  "total_size_human": "15.0 MB",
  "estimated_duration_seconds": 1.5,
  "estimated_duration_human": "2 sec",
  "files_by_category": {"documents": 10485760, "images": 5242880},
  "warning": null
}
```

#### 2. Créer un backup

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:9045/api/admin/backup
```

#### 3. Télécharger le backup

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:9045/api/admin/backup/download?backup_id={id}" \
  -o backup.zip
```

#### 4. Restaurer depuis un fichier

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@backup.zip" \
  -F "clear_existing=false" \
  http://localhost:9045/api/admin/restore
```

#### 5. Synchronisation avec le Hub

```bash
# Pousser vers le Hub
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:9045/api/admin/sync-to-hub

# Récupérer depuis le Hub
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"clear_existing": false}' \
  http://localhost:9045/api/admin/sync-from-hub
```

### Gestion des fichiers uploadés

Le template inclut un système de stockage de fichiers que les futures applications peuvent utiliser :

#### Modèle `UploadedFile`

```python
# Champs disponibles dans models.py
class UploadedFile(Base):
    filename: str           # Nom du fichier
    original_filename: str  # Nom original uploadé
    relative_path: str      # Chemin dans le storage
    size: int               # Taille en bytes
    mime_type: str          # Type MIME
    hash: str               # SHA-256 pour vérification
    category: str           # Catégorie (documents, images, etc.)
    description: str        # Description optionnelle
    owner: str              # Propriétaire (username)
    entity_type: str        # Type d'entité liée (optionnel)
    entity_id: int          # ID de l'entité liée (optionnel)
```

#### Utilisation du StorageManager

```python
from storage import storage_manager

# Sauvegarder un fichier uploadé
result = await storage_manager.save_file(
    file=upload_file,          # FastAPI UploadFile
    owner="username",
    category="documents"
)

# Lire un fichier
content = await storage_manager.read_file("username/documents/file.pdf")

# Lister les fichiers
files = await storage_manager.list_files(owner="username")

# Statistiques
stats = await storage_manager.get_storage_stats()
```

### Configuration du stockage

```env
# .env
UPLOADS_DIR=/app/uploads  # Répertoire de stockage (volume Docker)
```

### Pour les développeurs d'applications futures

Lors du développement d'une nouvelle application basée sur ce template :

1. **Utilisez `UploadedFile`** pour tracker tous les fichiers uploadés
2. **Associez les fichiers** à vos entités via `entity_type` et `entity_id`
3. **Utilisez `storage_manager`** pour toutes les opérations fichiers
4. **Catégorisez vos fichiers** pour une meilleure organisation
5. **Tout sera inclus automatiquement** dans les backups !

#### Exemple d'association fichier-entité

```python
# Dans votre endpoint d'upload
@app.post("/api/projects/{project_id}/documents")
async def upload_project_document(
    project_id: int,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(get_current_user)
):
    # Sauvegarder le fichier
    result = await storage_manager.save_file(
        file=file,
        owner=user.sub,
        category="project_documents"
    )
    
    # Enregistrer en BDD avec association
    uploaded_file = UploadedFile(
        filename=result["filename"],
        original_filename=result["original_filename"],
        relative_path=result["relative_path"],
        size=result["size"],
        mime_type=result["mime_type"],
        hash=result["hash"],
        category="project_documents",
        owner=user.sub,
        entity_type="project",      # Association au projet
        entity_id=project_id
    )
    db.add(uploaded_file)
    await db.commit()
    
    return {"file_id": uploaded_file.id}
```

### Endpoints Hub requis (côté Hub)

Pour que la synchronisation fonctionne, le Hub doit exposer :

```
POST /api/apps/{app_slug}/backup         # Recevoir un backup
GET  /api/apps/{app_slug}/backup/latest  # Retourner le dernier backup
GET  /api/apps/{app_slug}/backup/{id}    # Retourner un backup spécifique
```
