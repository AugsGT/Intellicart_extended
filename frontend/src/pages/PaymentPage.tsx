import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useCart } from '../context/CartContext'
import { useAuth } from '../context/AuthContext'
import { ApiError } from '../api/client'
import { newIdempotencyKey } from '../utils/idempotency'
import OrderSummary from '../components/OrderSummary'
import { createOrder } from '../api/orders'
import { trackCheckoutStarted } from '../api/events'
import type { PaymentMethod, ShippingAddress } from '../types/cart'
import './PaymentPage.css'

const SUCCESS_CARD = '4242 4242 4242 4242'

const EMPTY_ADDRESS: ShippingAddress = {
  full_name: '',
  address_line1: '',
  city: '',
  state: '',
  postal_code: '',
  phone: '',
}

function PaymentPage() {
  const { cart, loading, refresh } = useCart()
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()

  const [address, setAddress] = useState<ShippingAddress>(EMPTY_ADDRESS)
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('card')
  const [cardNumber, setCardNumber] = useState(SUCCESS_CARD)
  const [placing, setPlacing] = useState(false)
  const [placeError, setPlaceError] = useState<string | null>(null)
  // One key per attempt: pressing the button twice, or retrying after a timeout, cannot create two orders.
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey)

  useEffect(() => {
    if (cart && cart.items.length > 0) {
      trackCheckoutStarted().catch(() => {})
    }
    // Fire once when checkout is actually reached with items in the cart.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (loading || authLoading) {
    return (
      <div className="payment-page">
        <h1>Checkout</h1>
        <p>Loading cart...</p>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="payment-page">
        <h1>Checkout</h1>
        <div className="empty-cart">
          <p>Please log in to place your order. Your cart will be kept.</p>
          <Link to="/login" state={{ from: '/payment' }}>
            Log in →
          </Link>{' '}
          <Link to="/register" state={{ from: '/payment' }}>
            Register →
          </Link>
        </div>
      </div>
    )
  }

  const items = cart?.items ?? []

  if (items.length === 0) {
    return (
      <div className="payment-page">
        <h1>Payment</h1>
        <div className="empty-cart">
          <p>Your cart is empty — add something before checking out.</p>
          <Link to="/">Browse products →</Link>
        </div>
      </div>
    )
  }

  const addressComplete = Object.values(address).every((value) => value.trim() !== '')

  const handleAddressChange = (field: keyof ShippingAddress, value: string) => {
    setAddress((current) => ({ ...current, [field]: value }))
  }

  const handlePlaceOrder = async (e: FormEvent) => {
    e.preventDefault()
    if (!addressComplete) return

    setPlacing(true)
    setPlaceError(null)
    try {
      const order = await createOrder(address, paymentMethod, cardNumber, idempotencyKey)
      await refresh()
      navigate(`/orders/${order.id}`)
    } catch (err) {
      // The server gave a definite answer (declined, out of stock, invalid): the next press is a NEW attempt.
      // After a network failure we keep the key, so a retry cannot double-charge.
      if (err instanceof ApiError) setIdempotencyKey(newIdempotencyKey())
      // A declined card is saved as a FAILED order; show its page like a normal result.
      const failedOrder = err instanceof ApiError && err.status === 402 ? (err.body as { order?: { id: number } }).order : undefined
      if (failedOrder) {
        navigate(`/orders/${failedOrder.id}`)
        return
      }
      setPlaceError(err instanceof Error ? err.message : 'Could not place order')
      setPlacing(false)
    }
  }

  return (
    <div className="payment-page">
      <h1>Checkout</h1>

      <form className="checkout-layout" onSubmit={handlePlaceOrder}>
        <div className="checkout-form">
          <section>
            <h2>Shipping Address</h2>
            <div className="address-fields">
              <label>
                Full name
                <input
                  value={address.full_name}
                  onChange={(e) => handleAddressChange('full_name', e.target.value)}
                  required
                />
              </label>
              <label>
                Address
                <input
                  value={address.address_line1}
                  onChange={(e) => handleAddressChange('address_line1', e.target.value)}
                  required
                />
              </label>
              <label>
                City
                <input
                  value={address.city}
                  onChange={(e) => handleAddressChange('city', e.target.value)}
                  required
                />
              </label>
              <label>
                State
                <input
                  value={address.state}
                  onChange={(e) => handleAddressChange('state', e.target.value)}
                  required
                />
              </label>
              <label>
                Postal code
                <input
                  value={address.postal_code}
                  onChange={(e) => handleAddressChange('postal_code', e.target.value)}
                  required
                />
              </label>
              <label>
                Phone
                <input
                  type="tel"
                  value={address.phone}
                  onChange={(e) => handleAddressChange('phone', e.target.value)}
                  required
                />
              </label>
            </div>
          </section>

          <section>
            <h2>Payment Method</h2>
            <p className="mock-notice">This is a mock checkout — no real payment is processed.</p>
            <div className="payment-methods">
              <label className={`payment-method ${paymentMethod === 'card' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="payment-method"
                  checked={paymentMethod === 'card'}
                  onChange={() => setPaymentMethod('card')}
                />
                Credit / Debit Card
              </label>
              <label className={`payment-method ${paymentMethod === 'upi' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="payment-method"
                  checked={paymentMethod === 'upi'}
                  onChange={() => setPaymentMethod('upi')}
                />
                UPI
              </label>
              <label className={`payment-method ${paymentMethod === 'cod' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="payment-method"
                  checked={paymentMethod === 'cod'}
                  onChange={() => setPaymentMethod('cod')}
                />
                Cash on Delivery
              </label>
            </div>

            {paymentMethod === 'card' && (
              <div className="mock-card-fields">
                <input
                  placeholder="Card number (mock)"
                  value={cardNumber}
                  onChange={(e) => setCardNumber(e.target.value)}
                />
                <div className="mock-card-row">
                  <input placeholder="MM/YY" disabled value="12/30" />
                  <input placeholder="CVC" disabled value="123" />
                </div>
                <p className="mock-card-hint">
                  Try <code>4000 0000 0000 0002</code> to simulate a declined payment.
                </p>
              </div>
            )}
          </section>
        </div>

        <OrderSummary subtotal={cart!.subtotal} tax={cart!.tax} shipping={cart!.shipping} total={cart!.total}>
          <button type="submit" className="place-order-button" disabled={!addressComplete || placing}>
            {placing ? 'Placing order...' : 'Place Order'}
          </button>
          {!addressComplete && <p className="form-hint">Fill in your shipping address to continue.</p>}
          {placeError && <p className="form-hint error-message">{placeError}</p>}
        </OrderSummary>
      </form>
    </div>
  )
}

export default PaymentPage
