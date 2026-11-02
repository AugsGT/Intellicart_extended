import { Link } from 'react-router-dom'
import type { AdvisorCard, Comparison } from '../types/assistant'
import { trackRecommendationClick } from '../api/recommendations'
import { formatPrice } from '../utils/format'

interface CardsProps {
  cards: AdvisorCard[]
  onAskToAdd: (card: AdvisorCard) => void
  disabled: boolean
}

/** Product cards inside the conversation, each with the reasons it was suggested. */
export function AdvisorCards({ cards, onAskToAdd, disabled }: CardsProps) {
  return (
    <div className="advisor-cards">
      {cards.map((card) => (
        <div key={card.id} className="advisor-card">
          <div className="advisor-card-head">
            <strong>{card.name}</strong>
            <span className="advisor-price">{formatPrice(card.price)}</span>
          </div>
          <div className="advisor-card-sub">
            {card.brand && <span>{card.brand}</span>}
            <span className={`advisor-stock advisor-stock-${card.stock_status}`}>
              {card.stock_status === 'out_of_stock' ? 'Out of stock' : card.stock_status === 'low_stock' ? `Only ${card.stock} left` : 'In stock'}
            </span>
          </div>

          {card.explanation && (
            <details className="advisor-why">
              <summary>
                {card.explanation.match_summary} · {card.explanation.budget_note}
              </summary>
              <ul>
                {card.explanation.meets.map((text) => (
                  <li key={text} className="why-yes">✓ {text}</li>
                ))}
                {card.explanation.does_not_meet.map((text) => (
                  <li key={text} className="why-no">✗ {text}</li>
                ))}
                {card.explanation.info.map((text) => (
                  <li key={text} className="why-info">ℹ {text}</li>
                ))}
                {card.explanation.unknown.map((text) => (
                  <li key={text} className="why-unknown">? {text}</li>
                ))}
                <li className="why-warranty">{card.explanation.warranty.statement}</li>
              </ul>
            </details>
          )}

          <div className="advisor-card-actions">
            <Link to={`/products/${card.id}`} onClick={() => trackRecommendationClick('advisor', card.id)}>
              View product
            </Link>
            <button type="button" disabled={disabled || card.stock_status === 'out_of_stock'} onClick={() => onAskToAdd(card)}>
              Add to cart
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

/** Side-by-side comparison. It lists facts and per-attribute leaders; it never names an overall winner. */
export function ComparisonTable({ comparison }: { comparison: Comparison }) {
  return (
    <div className="advisor-comparison">
      <table>
        <thead>
          <tr>
            <th></th>
            {comparison.products.map((p) => (
              <th key={p.id}>{p.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {comparison.rows.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              {comparison.products.map((p) => (
                <td key={p.id}>{row.values[String(p.id)] ?? '-'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="advisor-leaders">
        {comparison.leaders.map((leader) => (
          <li key={leader.label}>
            <strong>{leader.label}:</strong> {leader.products.join(', ')}
          </li>
        ))}
      </ul>
    </div>
  )
}
