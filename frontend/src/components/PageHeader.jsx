/**
 * PageHeader — en-tête de page canonique (CSS-first, classes HUBCSS 0.3.0, zéro dépendance DS).
 *
 * Les 4 règles de la structure canonique :
 *   1. Un seul bouton retour par page (`back`).
 *   2. Une seule toolbar par page (rendue par la page, sous ce header).
 *   3. Une modal n'est pas une page — pas de PageHeader dans une modal.
 *   4. Pas de carte dans carte — PageHeader → toolbar → hub-panel, sans imbrication.
 *
 * Composition d'une page : <PageHeader /> → toolbar unique → hub-panel de contenu.
 * Le h1 de la page vient d'ici — ne jamais le doubler. Composant pur, sans état.
 */
import { APP_VERSION } from '../config'

function PageHeader({ title, back, badge, version = APP_VERSION, meta, actions }) {
  return (
    <header className="hub-page-header">
      {back && (
        <button
          type="button"
          className="hub-page-header-back"
          aria-label={back.label ?? 'Retour'}
          onClick={back.onClick}
        >
          ←
        </button>
      )}
      <div className="hub-page-header-heading">
        <div className="hub-page-header-titlerow">
          <h1 className="hub-page-header-title">{title}</h1>
          {badge && <span className="hub-page-header-badge">{badge}</span>}
        </div>
        {(version || meta) && (
          <div className="hub-page-header-meta">
            {version && <span className="hub-version-pill">v{version}</span>}
            {meta}
          </div>
        )}
      </div>
      {actions && <div className="hub-page-header-actions">{actions}</div>}
    </header>
  )
}

export { PageHeader }
export default PageHeader
