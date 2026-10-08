# Frontend — Recette de page canonique (HUBCSS)

Ce document décrit la structure canonique d'une page et les règles de composition UI du template. Le style est **CSS-first** : classes utilitaires `hub-*` fournies par le seed HUBCSS (`public/design-system/current/`), zéro dépendance obligatoire côté JS.

## Recette canonique

Toute page suit le même schéma DOM :

```
Header global (Header.jsx — branding, nav, thème)
└─ .container (routes/root.jsx)
   ├─ <PageHeader />        ← h1 de la page (ne jamais le doubler)
   ├─ toolbar unique        ← .hub-toolbar (recherche, boutons d'action)
   └─ hub-panel             ← .hub-panel [--padded] : le contenu
```

Le composant `components/PageHeader.jsx` matérialise l'en-tête de page :

| Prop | Rôle |
|---|---|
| `title` | Titre (requis) — rendu en `h1` |
| `back` | `{ label?, onClick }` — bouton retour unique |
| `badge` | Badge à côté du titre |
| `version` | Pill de version (défaut : `APP_VERSION`) |
| `meta` | Ligne méta sous le titre (compteur, statut…) |
| `actions` | Boutons d'action à droite |

`components/ExampleList.jsx` est la référence copiable de composition : PageHeader (rendu par la page) → toolbar unique → `hub-panel` avec `hub-table--striped`, skeleton de chargement, `hub-empty-state` et mutations via `useApiMutation`.

## Les 4 règles

1. **Un seul retour par page** — le bouton `back` du PageHeader ; pas de liens retour redondants.
2. **Une seule toolbar par page** — rendue par la page, sous le PageHeader.
3. **Une modal n'est pas une page** — pas de PageHeader dans une modal ; si le contenu demande des onglets ou une navigation, c'est une **route**.
4. **Pas de carte dans carte** — PageHeader → toolbar → `hub-panel`, sans imbrication (ex. `routes/demo/form.jsx` : FormDemo rend son propre `hub-panel--padded`, sans wrapper supplémentaire).

## Mapping classes socle → `hub-*`

Les classes "maison" dupliquant le design system ont été purgées d'`app.css` (seules restent les styles spécifiques au socle : `header*`, `app-*`, `container`, `message-*`, `token-display*`, `login-prompt`…). Correspondances appliquées dans le code :

| Classe template (supprimée) | Remplacement `hub-*` |
|---|---|
| `card` | `hub-panel hub-panel--padded` |
| `btn` / `btn-secondary` / `btn-danger` | `hub-button` / `+ hub-button-secondary` / `+ hub-button--danger` |
| `role-badge role-admin/user/viewer` | `hub-badge` + variante (`--pill`=admin, défaut=user, `hub-badge-success`=viewer, `hub-badge-warning`=manager) |
| `empty-state` (+ `-icon/-title/-description`) | `hub-empty-state` (+ mêmes modificateurs) |
| `category-badge` | `hub-badge` |
| `card-actions` | `hub-toolbar` (ou flex gap socle) |

Nouveau code : utiliser directement les classes `hub-*` — voir [`../HUBCSS/docs/HOW2USE.md`](../HUBCSS/docs/HOW2USE.md) (symlink ou checkout HUBCSS voisin).

## Matrice de consommation HUBCSS

| Besoin | Chemin |
|---|---|
| Structure + styles (template & apps) | Seed CSS `hub-*` — **défaut, zéro dépendance** |
| Composants React DS (StatCard, Modal…) | Option app : tarball `npm pack` → `vendor/` + dep `file:` (pattern lab-hubcss) + `setIconSpriteHref('/design-system/current/icons/lucide.svg')` au boot ; Dockerfiles : `COPY frontend/vendor/ ./vendor/` **avant** `npm install` |
| Registre npm privé | Verdaccio (`HUBCSS/docs/VERDACCIO.md`) pour les builds serveur air-gapped |

### Pattern vendor (option app)

Pour consommer la bibliothèque React du DS (`@poutchouli/design-system/react`) sans registre :

1. Dans HUBCSS : `npm run build` puis `npm pack`.
2. Copier le tarball dans `frontend/vendor/`.
3. Dépendance dans `frontend/package.json` : `"file:./vendor/<tarball>.tgz"`.
4. Appeler `setIconSpriteHref('/design-system/current/icons/lucide.svg')` au boot (le paquet ne porte pas le sprite).
5. Ajouter `COPY frontend/vendor/ ./vendor/` **avant** `npm install` dans les Dockerfiles — sinon le build échoue (fichier introuvable).

Référence complète : l'app `lab-hubcss`. Le seed CSS local reste le fallback de premier boot / hors-ligne ; en production, le bundle servi par le Hub (`/design-system/current/`) fait foi (voir HOW2USE).

### Gotcha Docker dev : `docker compose up -V`

Le volume anonyme `node_modules` **fige les dépendances** : après avoir changé un tarball placé dans `frontend/vendor/` (ou toute dep), faire `docker compose up -V` pour recréer le volume — sinon l'image tourne avec les anciennes deps malgré un `package.json` à jour.

Ré-exécuter INITIALISE sur un arbre déjà initialisé échoue désormais bruyamment (rebranding raté = erreur explicite) — INITIALISE est single-run.

## Sections de démonstration du template

| Route | Contenu |
|---|---|
| `/` (`routes/index.jsx`) | `PageHeader` + `ExampleList` (liste canonique : toolbar, table striped, empty state, pagination) |
| `/demo/form` (`routes/demo/form.jsx`) | `PageHeader` (retour) + `FormDemo` (TanStack Form, `hub-panel--padded`) — devtools en dev uniquement |
| `*` (`routes/notFound.jsx`) | `hub-empty-state` (Page introuvable) + bouton retour accueil |
