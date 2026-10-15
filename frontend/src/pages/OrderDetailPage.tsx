import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { cancelOrder, getOrder } from '../api/orders'
import type { Order } from '../types/cart'
import { formatPrice } from '../utils/format'
import './OrderDetailPage.css'

function OrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>()
  const [order, setOrder] = useState<Order | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [cancelError, setCancelError] = useState<string | null>(null)

  useEffect(() => {
    if (!orderId) return
    let cancelled = false

    getOrder(orderId)
      .then((data) => {
        if (!cancelled) setOrder(data)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [orderId])

  if (loading) return <p>Loading order...</p>

  if (error || !order) {
    return (
      <div className="order-detail-page">
        <h1>Order not found</h1>
        {error && <p className="error-message">{error}</p>}
        <Link to="/profile">← Back to order history</Link>
      </div>
    )
  }

  const failed = order.status === 'FAILED'
  const cancelled = order.status === 'CANCELLED'

  const handleCancel = async () => {
    if (!window.confirm('Cancel this order?')) return
    try {
      setOrder(await cancelOrder(order.id))
    } catch (err) {
      setCancelError(err instanceof Error ? err.message : 'Could not cancel order')
    }
  }

  return (
    <div className="order-detail-page">
      <div className={`confirmation-banner ${failed ? 'failed-banner' : ''}`}>
        <h1>{failed ? 'Payment Failed ❌' : cancelled ? 'Order Cancelled' : 'Order Confirmed 🎉'}</h1>
        <p>
          {failed ? (
            <>
              Order <strong>#{order.id}</strong> couldn't be charged — your cart was left untouched, so you can{' '}
              <Link to="/payment">try again</Link>.
            </>
          ) : (
            <>
              Order <strong>#{order.id}</strong> was placed on {new Date(order.created_at).toLocaleString()}. Status:{' '}
              <strong>{order.status.toLowerCase()}</strong>.
            </>
          )}
        </p>
      </div>

      <div className="order-detail-layout">
        <div>
          <section>
            <h2>Items</h2>
            <ul className="order-items">
              {order.items.map((item) => (
                <li key={item.id}>
                  <span>
                    {item.name} × {item.quantity}
                  </span>
                  <span>{formatPrice(item.line_total)}</span>
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2>Shipping Address</h2>
            <p className="address-block">
              {order.full_name}
              <br />
              {order.address_line1}
              <br />
              {order.city}, {order.state} {order.postal_code}
              <br />
              {order.phone}
            </p>
          </section>

          <section>
            <h2>Payment Method</h2>
            <p>
              {order.payment_method === 'card' && 'Credit / Debit Card'}
              {order.payment_method === 'upi' && 'UPI'}
              {order.payment_method === 'cod' && 'Cash on Delivery'}
              {' — mock payment, nothing was charged.'}
            </p>
          </section>
        </div>

        <div className="order-total-card">
          <div className="summary-row">
            <span>Subtotal</span>
            <span>{formatPrice(order.subtotal)}</span>
          </div>
          <div className="summary-row">
            <span>Tax</span>
            <span>{formatPrice(order.tax)}</span>
          </div>
          <div className="summary-row">
            <span>Shipping</span>
            <span>{parseFloat(order.shipping) === 0 ? 'Free' : formatPrice(order.shipping)}</span>
          </div>
          <div className="summary-row summary-total">
            <span>Total</span>
            <span>{formatPrice(order.total)}</span>
          </div>
        </div>
      </div>

      {order.status === 'CONFIRMED' && (
        <button type="button" className="cancel-order-button" onClick={handleCancel}>
          Cancel order
        </button>
      )}
      {cancelError && <p className="error-message">{cancelError}</p>}

      <Link to="/" className="continue-shopping-link">
        ← Continue shopping
      </Link>
    </div>
  )
}

export default OrderDetailPage
