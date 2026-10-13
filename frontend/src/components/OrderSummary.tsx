import type { ReactNode } from 'react'
import { formatPrice } from '../utils/format'
import { FREE_SHIPPING_THRESHOLD } from '../utils/cart'
import './OrderSummary.css'

interface OrderSummaryProps {
  subtotal: string
  tax: string
  shipping: string
  total: string
  children?: ReactNode
}

function OrderSummary({ subtotal, tax, shipping, total, children }: OrderSummaryProps) {
  const shippingValue = parseFloat(shipping)
  const subtotalValue = parseFloat(subtotal)

  return (
    <div className="order-summary">
      <h2>Order Summary</h2>
      <dl>
        <div className="summary-row">
          <dt>Subtotal</dt>
          <dd>{formatPrice(subtotal)}</dd>
        </div>
        <div className="summary-row">
          <dt>Tax (18%)</dt>
          <dd>{formatPrice(tax)}</dd>
        </div>
        <div className="summary-row">
          <dt>Shipping</dt>
          <dd>{shippingValue === 0 ? 'Free' : formatPrice(shipping)}</dd>
        </div>
        {shippingValue > 0 && (
          <p className="free-shipping-hint">
            Add {formatPrice(FREE_SHIPPING_THRESHOLD - subtotalValue)} more for free shipping.
          </p>
        )}
        <div className="summary-row summary-total">
          <dt>Total</dt>
          <dd>{formatPrice(total)}</dd>
        </div>
      </dl>
      {children}
    </div>
  )
}

export default OrderSummary
