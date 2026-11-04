# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""HUBapp Template — app fine de démonstration sur socle POULIDOR.

Le socle (hub_socle) fournit tout le transverse : auth JWT/JWKS, config,
database + migrations, hub_client M2M, backup/restore, outbox, SSE,
endpoints core (santé/version/jwks), CRUD démo (items), préférences,
catalogue M2M + allowlist IA (m2m_share.yaml).

Cette app n'ajoute RIEN : c'est le gabarit minimal. Une vraie app :
1. crée ses routes dans backend/routes/ et les passe à create_app(routers=[...]) ;
2. déclare ses modèles métier (Base du socle) et ses settings via
   register_settings_extra AVANT d'importer ses routes ;
3. override son storage si besoin via services_overrides={"storage": ...}.

Contrat complet : HUBsocle/docs/REFERENCE-APP-FINE.md
"""
import logging

from hub_socle import create_app

logger = logging.getLogger(__name__)

app = create_app()


if __name__ == "__main__":
    # Dev hors conteneur uniquement (en conteneur, l'entrypoint du socle
    # lance `uvicorn main:app`).
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
