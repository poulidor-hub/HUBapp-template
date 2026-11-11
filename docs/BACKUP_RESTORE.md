# 📦 Guide de Backup/Restore avec le Hub

Ce document explique comment configurer et utiliser le système de backup/restore générique intégré aux applications connectées au Hub.

---

## 📋 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Prérequis](#prérequis)
3. [Configuration](#configuration)
4. [Endpoints disponibles](#endpoints-disponibles)
5. [Utilisation](#utilisation)
6. [Format du backup](#format-du-backup)
7. [Synchronisation avec le Hub](#synchronisation-avec-le-hub)
8. [Restauration](#restauration)
9. [Dépannage](#dépannage)

---

## 🎯 Vue d'ensemble

Le système de backup/restore est **générique** : il découvre automatiquement toutes les tables de la base de données et les sauvegarde sans configuration manuelle.

### Fonctionnalités

- ✅ Découverte automatique de toutes les tables PostgreSQL
- ✅ Sérialisation des types complexes (datetime, date, Decimal, bytes)
- ✅ Compression ZIP des données
- ✅ Inclusion des fichiers uploadés
- ✅ Synchronisation bidirectionnelle avec le Hub
- ✅ Restauration avec upsert (INSERT ... ON CONFLICT)
- ✅ Checksum SHA-256 pour vérification d'intégrité

### Architecture

```
┌─────────────────────┐         ┌─────────────────────┐
│   Application 1     │◄───────►│        HUB          │
│  (ex: exemple-app)│         │                     │
└─────────────────────┘         │  ┌───────────────┐  │
                                │  │   Stockage    │  │
┌─────────────────────┐         │  │   Backups     │  │
│   Application 2     │◄───────►│  └───────────────┘  │
│  (ex: Telecom)      │         │                     │
└─────────────────────┘         └─────────────────────┘
                                         ▲
┌─────────────────────┐                  │
│   Application N     │◄─────────────────┘
│                     │
└─────────────────────┘
```

---

## ⚙️ Prérequis

### 1. Application enregistrée auprès du Hub

L'application doit être enregistrée avec `IS_SHARED=true` dans son fichier `.env` :

```env
# Configuration Hub
HUB_URL=https://hub.example.com
HUB_SERVICE_ACCOUNT_FILE=/app/secrets/service_account.json
IS_SHARED=true
```

### 2. Fichier service account

Le fichier `service_account.json` doit contenir les credentials M2M :

```json
{
  "client_id": "votre-app-slug",
  "client_secret": "secret-généré-par-le-hub",
  "hub_url": "https://hub.example.com"
}
```

### 3. Base de données PostgreSQL

Le système utilise des requêtes spécifiques PostgreSQL :
- `information_schema.tables` pour la découverte des tables
- `ON CONFLICT ... DO UPDATE` pour l'upsert

---

## 🔧 Configuration

### Variables d'environnement

| Variable | Description | Exemple |
|----------|-------------|---------|
| `HUB_URL` | URL du Hub central | `https://hub.hub.example.lan` |
| `HUB_SERVICE_ACCOUNT_FILE` | Chemin du fichier credentials | `/app/secrets/service_account.json` |
| `IS_SHARED` | Mode partagé (backup activé) | `true` |
| `APP_SLUG` | Identifiant unique de l'app | `exemple-apps` |

### Tables exclues automatiquement

Certaines tables système sont exclues du backup :

```python
EXCLUDED_TABLES = {
    "alembic_version",  # Migrations Alembic
    "spatial_ref_sys",  # PostGIS
}
```

---

## 🔌 Endpoints disponibles

Tous les endpoints sont protégés et nécessitent le rôle `admin`.

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/admin/backup/estimate` | Estimer taille et durée |
| `POST` | `/api/admin/backup` | Créer un backup |
| `GET` | `/api/admin/backup/download?backup_id=xxx` | Télécharger le ZIP |
| `POST` | `/api/admin/restore` | Restaurer depuis un fichier |
| `POST` | `/api/admin/sync-to-hub` | Pousser vers le Hub |
| `POST` | `/api/admin/sync-from-hub` | Récupérer depuis le Hub |
| `GET` | `/api/admin/backup/list` | Lister les backups locaux |
| `DELETE` | `/api/admin/backup/{backup_id}` | Supprimer un backup local |

---

## 📖 Utilisation

### 1. Estimer un backup

Avant de créer un backup, vous pouvez estimer sa taille :

```bash
curl -X GET "https://app.example.com/api/admin/backup/estimate" \
  -H "Authorization: Bearer <token>"
```

**Réponse :**

```json
{
  "tables": {
    "items": 150,
    "user_preferences": 25,
    "uploaded_files": 42,
    "services": 89
  },
  "total_tables": 4,
  "total_rows": 306,
  "total_files": 42,
  "database_size_bytes": 122400,
  "files_size_bytes": 5242880,
  "total_size_bytes": 5901708,
  "total_size_human": "5.6 MB",
  "estimated_duration_seconds": 0.56,
  "estimated_duration_human": "1 sec",
  "warning": null
}
```

### 2. Créer un backup

```bash
curl -X POST "https://app.example.com/api/admin/backup" \
  -H "Authorization: Bearer <token>"
```

**Réponse :**

```json
{
  "success": true,
  "message": "Backup créé avec succès",
  "metadata": {
    "backup_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "app_slug": "exemple-apps",
    "app_version": "3.2.0",
    "created_at": "2026-02-01T10:30:00",
    "created_by": "admin",
    "format_version": "3.0",
    "total_tables": 4,
    "total_rows": 306,
    "total_files": 42,
    "total_size_bytes": 5901708,
    "total_size_human": "5.6 MB",
    "checksum": "sha256:abc123...",
    "table_stats": {
      "items": 150,
      "user_preferences": 25,
      "uploaded_files": 42,
      "services": 89
    }
  },
  "download_url": "/api/admin/backup/download?backup_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### 3. Télécharger un backup

```bash
curl -X GET "https://app.example.com/api/admin/backup/download?backup_id=xxx" \
  -H "Authorization: Bearer <token>" \
  -o backup.zip
```

### 4. Restaurer depuis un fichier

```bash
curl -X POST "https://app.example.com/api/admin/restore" \
  -H "Authorization: Bearer <token>" \
  -F "file=@backup.zip" \
  -F "clear_existing=false"
```

**Paramètres :**

| Paramètre | Type | Description |
|-----------|------|-------------|
| `file` | File | Fichier ZIP du backup |
| `clear_existing` | string | `"true"` pour supprimer les données existantes |

**Réponse :**

```json
{
  "success": true,
  "message": "Restauration terminée avec succès",
  "format_version": "3.0",
  "tables_restored": {
    "items": {"imported": 150, "updated": 0, "skipped": 0},
    "user_preferences": {"imported": 25, "updated": 0, "skipped": 0},
    "services": {"imported": 89, "updated": 0, "skipped": 0}
  },
  "total_tables": 3,
  "total_imported": 264,
  "total_updated": 0,
  "total_skipped": 0,
  "files_restored": 42,
  "errors": [],
  "warnings": []
}
```

---

## 📁 Format du backup

### Structure du fichier ZIP

```
backup_xxx.zip
├── data.json           # Données structurées (toutes les tables)
└── files/              # Fichiers uploadés
    └── owner/
        └── category/
            └── filename.ext
```

### Structure de data.json

```json
{
  "metadata": {
    "backup_id": "uuid",
    "app_slug": "exemple-apps",
    "app_version": "3.2.0",
    "created_at": "2026-02-01T10:30:00",
    "created_by": "admin",
    "format_version": "3.0",
    "tables": ["items", "user_preferences", "services"],
    "table_stats": {
      "items": 150,
      "user_preferences": 25,
      "services": 89
    }
  },
  "data": {
    "items": [
      {
        "id": 1,
        "title": "Mon item",
        "created_at": {"__type__": "datetime", "value": "2026-01-15T08:00:00"},
        "...": "..."
      }
    ],
    "user_preferences": [...],
    "services": [...]
  }
}
```

### Sérialisation des types complexes

Les types non-JSON sont sérialisés avec un marqueur `__type__` :

| Type Python | Sérialisation JSON |
|-------------|-------------------|
| `datetime` | `{"__type__": "datetime", "value": "2026-02-01T10:30:00"}` |
| `date` | `{"__type__": "date", "value": "2026-02-01"}` |
| `Decimal` | `{"__type__": "decimal", "value": "123.45"}` |
| `bytes` | `{"__type__": "bytes", "value": "base64..."}` |

---

## ☁️ Synchronisation avec le Hub

### Pousser un backup vers le Hub

```bash
curl -X POST "https://app.example.com/api/admin/sync-to-hub" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"description": "Backup avant mise à jour"}'
```

**Réponse :**

```json
{
  "success": true,
  "message": "Backup synchronisé avec le Hub",
  "detail": "Backup ID: xxx, Tables: 4, Enregistrements: 306, Taille: 5.6 MB",
  "backup_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "metadata": {...}
}
```

### Récupérer et restaurer depuis le Hub

```bash
curl -X POST "https://app.example.com/api/admin/sync-from-hub" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"clear_existing": true}'
```

**Paramètres :**

| Paramètre | Type | Description |
|-----------|------|-------------|
| `backup_id` | string | ID spécifique (optionnel, sinon le dernier) |
| `clear_existing` | bool | Supprimer les données existantes |

**Processus :**

1. L'application demande au Hub le dernier backup
2. Le Hub appelle `POST /api/admin/restore` sur l'application
3. L'application restaure toutes les tables automatiquement

---

## 🔄 Restauration

### Mode Upsert (par défaut)

Sans `clear_existing=true`, la restauration utilise un **upsert** :

```sql
INSERT INTO "table" (col1, col2, ...)
VALUES (:col1, :col2, ...)
ON CONFLICT (primary_key)
DO UPDATE SET col1 = EXCLUDED.col1, col2 = EXCLUDED.col2, ...
```

Cela permet de :
- ✅ Insérer les nouvelles lignes
- ✅ Mettre à jour les lignes existantes
- ✅ Conserver les données non présentes dans le backup

### Mode Clear (suppression préalable)

Avec `clear_existing=true` :

1. Les contraintes FK sont temporairement désactivées
2. Toutes les données des tables concernées sont supprimées
3. Les données du backup sont importées
4. Les contraintes FK sont réactivées

⚠️ **Attention** : Cette option supprime TOUTES les données existantes !

### Gestion des colonnes manquantes

Si une table a évolué entre le backup et la restauration :

- **Nouvelles colonnes** : Ignorées (utiliseront les valeurs par défaut)
- **Colonnes supprimées** : Ignorées (données perdues)
- **Tables manquantes** : Avertissement dans `warnings`

---

## 🛠️ Dépannage

### Erreur : "Application non enregistrée auprès du Hub"

**Cause** : Le Hub n'a pas de connexion active avec l'application.

**Solution** :
1. Vérifier `IS_SHARED=true` dans `.env`
2. Vérifier le fichier `service_account.json`
3. Redémarrer l'application pour forcer l'enregistrement
4. Consulter les logs : `docker logs backend`

### Erreur : "Backup non trouvé"

**Cause** : L'ID de backup n'existe pas ou a été supprimé.

**Solution** :
1. Lister les backups disponibles : `GET /api/admin/backup/list`
2. Vérifier sur le Hub si le backup existe

### Erreur : "Table 'xxx' du backup n'existe pas"

**Cause** : Le schéma de la base a changé depuis le backup.

**Solution** :
1. Vérifier que les migrations sont à jour
2. Le warning n'empêche pas la restauration des autres tables

### Restauration lente

**Cause** : Trop de données ou contraintes FK complexes.

**Solutions** :
1. Utiliser `clear_existing=true` (plus rapide car pas d'upsert)
2. Désactiver temporairement les triggers si présents

### Fichiers manquants après restauration

**Cause** : Les fichiers n'étaient pas dans le ZIP ou erreur de lecture.

**Solution** :
1. Vérifier `warnings` dans la réponse
2. S'assurer que le storage est accessible
3. Vérifier les permissions sur le dossier de stockage

---

## 📊 Logs

Les opérations de backup/restore génèrent des logs détaillés :

```
📦 Création du backup générique abc123 par admin
📊 Tables découvertes: ['items', 'user_preferences', 'services']
  ✓ items: 150 enregistrements
  ✓ user_preferences: 25 enregistrements
  ✓ services: 89 enregistrements
✅ Backup générique abc123 créé: 3 tables, 264 enregistrements total, 42 fichiers (5.6 MB)
   Tables avec données: ['items', 'user_preferences', 'services']
```

```
🔄 Restauration générique démarrée par admin (clear_existing=false)
📂 Backup abc123 - App: exemple-apps, Version: 3.2.0, Format: 3.0
📊 Tables dans le backup: ['items', 'user_preferences', 'services']
📊 Tables existantes dans la base: ['items', 'user_preferences', 'services', 'new_table']
  ✓ items: 150 importés, 0 mis à jour, 0 ignorés
  ✓ user_preferences: 25 importés, 0 mis à jour, 0 ignorés
  ✓ services: 89 importés, 0 mis à jour, 0 ignorés
✅ Restauration terminée: 3 tables, 264 importés, 0 mis à jour, 42 fichiers
```

---

## 🔐 Sécurité

- Tous les endpoints nécessitent le rôle `admin`
- Les backups sont stockés temporairement et peuvent être supprimés
- Les checksums SHA-256 permettent de vérifier l'intégrité
- La communication avec le Hub utilise l'authentification M2M (OAuth2)

---

## 📚 Références

- [API Hub - Documentation](/docs/HUB_API.md)
- [Authentification M2M](/docs/M2M_AUTH.md)
- [Storage Manager](/docs/STORAGE.md)
