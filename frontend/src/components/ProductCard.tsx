import { useState, type MouseEvent } from 'react'
import { Link } from 'react-router-dom'
import type { Product } from '../types/product'
import { formatPrice, getStockStatus } from '../utils/format'
import { useCart } from '../context/CartContext'
import './ProductCard.css'

function ProductCard({ product }: { product: Product }) {
  const stock = getStockStatus(product.stock, product.stock_status)
  const { cart, addItem } = useCart()
  const [justAdded, setJustAdded] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  const inCartQuantity = cart?.items.find((item) => item.product_id === product.id)?.quantity ?? 0
  const atStockLimit = inCartQuantity >= product.stock

  const handleAddToCart = async (e: MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setAddError(null)
    try {
      await addItem(product.id)
      setJustAdded(true)
      setTimeout(() => setJustAdded(false), 1200)
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Could not add to cart')
      setTimeout(() => setAddError(null), 2000)
    }
  }

  return (
    <Link to={`/products/${product.id}`} className="product-card">
      <div className="product-image">
        {product.image ? (
          <img src={product.image} alt={product.name} />
        ) : (
          <span className="product-image-placeholder">No image</span>
        )}
      </div>
      <div className="product-body">
        <span className="product-category">
          {product.category_name}
        </span>
        <h3 className="product-name">{product.name}</h3>
        {product.brand && <span className="product-brand">{product.brand}</span>}
        {product.description && <p className="product-description">{product.description}</p>}
        <div className="product-footer">
          <span className="product-price">{formatPrice(product.price)}</span>
          <span className={`stock-badge ${stock.className}`}>{stock.label}</span>
        </div>
        <button
          type="button"
          className="add-to-cart-button"
          onClick={handleAddToCart}
          disabled={product.stock === 0 || atStockLimit}
        >
          {addError
            ? addError
            : product.stock === 0
              ? 'Out of stock'
              : justAdded
                ? 'Added ✓'
                : atStockLimit
                  ? 'Max in cart'
                  : 'Add to Cart'}
        </button>
      </div>
    </Link>
  )
}

export default ProductCard
