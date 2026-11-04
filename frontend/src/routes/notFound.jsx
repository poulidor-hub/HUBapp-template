// SPDX-License-Identifier: MIT
// Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

import { Link } from '@tanstack/react-router'

const SPRITE = '/design-system/current/icons/lucide.svg'

export default function NotFoundPage() {
  return (
    <div className="hub-empty-state">
      <div className="hub-empty-state-icon">
        <svg className="hub-icon" aria-hidden="true">
          <use href={`${SPRITE}#icon-signpost`} />
        </svg>
      </div>
      <p className="hub-empty-state-title">Page introuvable</p>
      <p className="hub-empty-state-description">
        La page demandée n'existe pas ou a été déplacée.
      </p>
      <Link to="/" className="hub-button">Retour à l'accueil</Link>
    </div>
  )
}
