# Migration M2M — procédure canari volontaire

Pour activer le mode renforcé M2M (slug enforcement) sur **une** application
existante sans impacter les autres.

## Prérequis

- Hub ≥ 3.12.0 (ou branche `fix/release-1-m2m-enforcement`)
- Template ≥ 2.6.0 (ou branche `fix/release-1-template-fixes`)
- Application atelier (workshop) créée pour le test

## Étape 1 — Sauvegarde

```bash
./hubctl work <slug>          # Atelier avec clone DB
cd HUB_base && make backup    # Sauvegarde Hub complète
```

## Étape 2 — Activation sur l'app canari

1. Dans l'interface admin Hub, éditer l'application cible.
2. Passer le champ `m2m_enforcement_mode` de `compat` à `enforced`.
3. Ou via API :
   ```bash
   curl -X PATCH "$HUB/api/apps/$APP_ID" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"m2m_enforcement_mode": "enforced"}'
   ```

## Étape 3 — Vérifications

- [ ] Login SSO : fonctionne.
- [ ] Réinscription de l'app avec un token SA valide : acceptée.
- [ ] Tentative de réinscription avec un SA d'une autre app : refusée (403).
- [ ] Push des dépendances M2M avec X-Slug possédé : accepté.
- [ ] Push avec X-Slug non possédé : refusé (403).
- [ ] Outbox Hub : `/api/outbox/*` réservé admin.
- [ ] Outbox app : les 4xx restent en failed (retry), pas marqués livrés.
- [ ] AuthProvider app : démarre sans erreur TDZ (plus de ReferenceError).
- [ ] Aucun secret/token dans les logs d'audit (`audit_logs.action`).

## Étape 4 — Rollback

```bash
curl -X PATCH "$HUB/api/apps/$APP_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"m2m_enforcement_mode": "compat"}'
```

L'application revient immédiatement au mode compatibilité sans
redémarrage ni perte de données.

## Étape 5 — Généralisation

Après validation canari :

1. Activer `enforced` sur une deuxième app.
2. Attendre 24 h, vérifier les logs d'audit et l'outbox.
3. Répéter jusqu'à couverture complète du parc.
