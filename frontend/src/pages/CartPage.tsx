import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useCart } from '../context/CartContext'
import QuantityStepper from '../components/QuantityStepper'
import OrderSummary from '../components/OrderSummary'
import RecommendationSection from '../components/RecommendationSection'
import { getCartBasedRecommendations } from '../api/recommendations'
import type { Product } from '../types/product'
import { formatPrice } from '../utils/format'
import './CartPage.css'

function CartPage() {
  const { cart, loading, error, removeItem, setQuantity } = useCart()
  const navigate = useNavigate()
  const [recommended, setRecommended] = useState<Product[]>([])

  useEffect(() => {
    if (!cart || cart.items.length === 0) return
    getCartBasedRecommendations()
      .then(setRecommended)
      .catch(() => {})
  }, [cart])

  if (loading) {
    return (
      <div className="cart-page">
        <h1>Cart</h1>
        <p>Loading cart...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="cart-page">
        <h1>Cart</h1>
        <p className="error-message">Couldn't load your cart: {error}</p>
      </div>
    )
  }

  const items = cart?.items ?? []

  if (items.length === 0) {
    return (
      <div className="cart-page">
        <h1>Cart</h1>
        <div className="empty-cart">
          <p>Your cart is empty.</p>
          <Link to="/">Browse products →</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="cart-page">
      <h1>Cart</h1>

      <div className="cart-layout">
        <ul className="cart-items">
          {items.map((item) => (
            <li key={item.id} className="cart-item">
              <div className="cart-item-image">
                {item.image ? (
                  <img src={item.image} alt={item.name} />
                ) : (
                  <span className="product-image-placeholder">No image</span>
                )}
              </div>

              <div className="cart-item-info">
                <Link to={`/products/${item.product_id}`} className="cart-item-name">
                  {item.name}
                </Link>
                <span className="cart-item-price">{formatPrice(item.price)} each</span>
                {item.stock === 0 && <span className="cart-item-warning">No longer in stock</span>}
              </div>

              <QuantityStepper
                quantity={item.quantity}
                max={item.stock}
                onChange={(quantity) => setQuantity(item.id, quantity)}
              />

              <span className="cart-item-line-total">{formatPrice(item.line_total)}</span>

              <button
                type="button"
                className="remove-button"
                onClick={() => removeItem(item.id)}
                aria-label={`Remove ${item.name}`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>

        <OrderSummary subtotal={cart!.subtotal} tax={cart!.tax} shipping={cart!.shipping} total={cart!.total}>
          <button type="button" className="checkout-button" onClick={() => navigate('/payment')}>
            Proceed to Checkout
          </button>
        </OrderSummary>
      </div>

      <RecommendationSection title="You might also like" icon="✨" kind="cart_based" products={recommended} />
    </div>
  )
}

export default CartPage
