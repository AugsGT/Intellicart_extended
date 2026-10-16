import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { clickIntervention, getActiveIntervention, dismissIntervention, type ActiveIntervention } from '../api/interventions'
import './InterventionBanner.css'

const ACTION_CTA: Record<string, { label: string; to: string }> = {
  REMINDER: { label: 'View cart', to: '/cart' },
  CHECKOUT_REMINDER: { label: 'Back to checkout', to: '/payment' },
  STOCK_ALTERNATIVE: { label: 'See options', to: '/cart' },
}

function InterventionBanner() {
  const [intervention, setIntervention] = useState<ActiveIntervention | null>(null)

  useEffect(() => {
    getActiveIntervention()
      .then(setIntervention)
      .catch(() => {})
  }, [])

  if (!intervention) return null

  const productId = intervention.signals?.product_id
  const cta =
    intervention.action === 'BACK_IN_STOCK_ALERT' && typeof productId === 'number'
      ? { label: 'View product', to: `/products/${productId}` }
      : ACTION_CTA[intervention.action]

  const handleDismiss = () => {
    dismissIntervention(intervention.id).catch(() => {})
    setIntervention(null)
  }

  return (
    <div className="intervention-banner" role="status">
      <span className="intervention-message">{intervention.message}</span>
      <div className="intervention-actions">
        {cta && (
          <Link to={cta.to} className="intervention-cta" onClick={() => clickIntervention(intervention.id).catch(() => {})}>
            {cta.label}
          </Link>
        )}
        <button type="button" className="intervention-dismiss" onClick={handleDismiss} aria-label="Dismiss">
          ✕
        </button>
      </div>
    </div>
  )
}

export default InterventionBanner
