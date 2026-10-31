import type { Product } from '../types/product'
import { trackRecommendationClick, type RecommendationKind } from '../api/recommendations'
import ProductCard from './ProductCard'
import './RecommendationSection.css'

interface RecommendationSectionProps {
  title: string
  icon?: string
  kind: RecommendationKind
  products: Product[]
}

function RecommendationSection({ title, icon, kind, products }: RecommendationSectionProps) {
  if (products.length === 0) return null

  return (
    <section className="recommendation-section">
      <h2>
        {icon && <span className="recommendation-icon">{icon}</span>} {title}
      </h2>
      <div className="recommendation-row">
        {products.map((product) => (
          // Capture the click so we can report it, then let the card navigate as usual.
          <div
            key={product.id}
            className="recommendation-card"
            onClickCapture={() => trackRecommendationClick(kind, product.id)}
          >
            <ProductCard product={product} />
            {product.reason && <p className="recommendation-reason">{product.reason}</p>}
          </div>
        ))}
      </div>
    </section>
  )
}

export default RecommendationSection
