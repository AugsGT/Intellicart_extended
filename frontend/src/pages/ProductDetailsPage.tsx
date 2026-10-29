import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getProduct } from '../api/products'
import { getSimilarProducts, getFrequentlyBoughtTogether, getSubstitutes } from '../api/recommendations'
import type { Product } from '../types/product'
import { formatPrice, getStockStatus } from '../utils/format'
import { useCart } from '../context/CartContext'
import RecommendationSection from '../components/RecommendationSection'
import './ProductDetailsPage.css'

// Number specs arrive as decimal strings ("16.00"); show them without trailing zeros ("16").
function formatAttributeValue(value: string | number): string {
  return /^-?\d+\.\d+$/.test(String(value)) ? String(parseFloat(String(value))) : String(value)
}

function ProductDetailsPage() {
  const { id } = useParams<{ id: string }>()
  const [product, setProduct] = useState<Product | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [similar, setSimilar] = useState<Product[]>([])
  const [frequentlyBought, setFrequentlyBought] = useState<Product[]>([])
  const [substitutes, setSubstitutes] = useState<Product[]>([])
  const { cart, addItem } = useCart()
  const [justAdded, setJustAdded] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false

    setLoading(true)
    setError(null)

    getProduct(id)
      .then((data) => {
        if (!cancelled) setProduct(data)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    getSimilarProducts(Number(id))
      .then((data) => !cancelled && setSimilar(data))
      .catch(() => {})
    getFrequentlyBoughtTogether(Number(id))
      .then((data) => !cancelled && setFrequentlyBought(data))
      .catch(() => {})
    getSubstitutes(Number(id))
      .then((data) => !cancelled && setSubstitutes(data))
      .catch(() => {})

    return () => {
      cancelled = true
    }
  }, [id])

  if (loading) return <p>Loading product...</p>
  if (error) return <p className="error-message">Couldn't load this product: {error}</p>
  if (!product) return null

  const stock = getStockStatus(product.stock, product.stock_status)
  const inCartQuantity = cart?.items.find((item) => item.product_id === product.id)?.quantity ?? 0
  const atStockLimit = inCartQuantity >= product.stock

  const handleAddToCart = async () => {
    setAddError(null)
    try {
      await addItem(product.id)
      setJustAdded(true)
      setTimeout(() => setJustAdded(false), 1200)
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Could not add to cart')
    }
  }

  return (
    <div className="product-details">
      <Link to="/" className="back-link">
        ← Back to products
      </Link>

      <div className="product-details-layout">
        <div className="product-details-image">
          {product.image ? (
            <img src={product.image} alt={product.name} />
          ) : (
            <span className="product-image-placeholder">No image</span>
          )}
        </div>

        <div className="product-details-info">
          <span className="product-category">
            {product.category_name}
          </span>
          <h1>{product.name}</h1>
          {product.brand && <p className="product-brand">by {product.brand}</p>}
          <p className="product-price">{formatPrice(product.price)}</p>
          <span className={`stock-badge ${stock.className}`}>{stock.label}</span>
          {product.description && <p className="product-description">{product.description}</p>}

          <button
            type="button"
            className="add-to-cart-button"
            onClick={handleAddToCart}
            disabled={product.stock === 0 || atStockLimit}
          >
            {product.stock === 0 ? 'Out of stock' : justAdded ? 'Added ✓' : atStockLimit ? 'Max in cart' : 'Add to Cart'}
          </button>
          {addError && <p className="error-message">{addError}</p>}
          {justAdded && (
            <Link to="/cart" className="view-cart-link">
              View cart →
            </Link>
          )}

          {substitutes.length > 0 && (
            <p className="substitute-hint">
              Running low on stock — {product.stock === 0 ? "it's currently out" : 'only a few left'}. See in-stock
              alternatives below.
            </p>
          )}

          {product.attributes.length > 0 && (
            <dl className="product-meta">
              {product.attributes.map((attribute) => (
                <div key={attribute.key} className="product-meta-row">
                  <dt>{attribute.label}</dt>
                  <dd>
                    {formatAttributeValue(attribute.value)}
                    {attribute.unit ? ` ${attribute.unit}` : ''}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>

      <RecommendationSection title="In Stock Alternatives" icon="⚡" kind="substitutes" products={substitutes} />
      <RecommendationSection title="Frequently Bought Together" icon="🛒" kind="frequently_bought_together" products={frequentlyBought} />
      <RecommendationSection title="Similar Products" icon="✨" kind="similar" products={similar} />
    </div>
  )
}

export default ProductDetailsPage
