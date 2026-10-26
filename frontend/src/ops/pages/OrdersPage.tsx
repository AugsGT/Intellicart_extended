import { Fragment, useEffect, useState } from 'react'
import { listAllOrders, updateOrderStatus } from '../api'
import type { Order, OrderStatus } from '../../types/cart'
import { formatPrice, formatDateTime } from '../../utils/format'

// Mirrors the server's allowed transitions (apps/orders/services.py). The server
// is the one that actually enforces them; this only limits what the dropdown offers.
const NEXT_STATUSES: Record<OrderStatus, OrderStatus[]> = {
  CONFIRMED: ['SHIPPED', 'CANCELLED'],
  SHIPPED: ['DELIVERED', 'CANCELLED'],
  DELIVERED: [],
  CANCELLED: [],
  FAILED: [],
}

function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [updating, setUpdating] = useState<number | null>(null)

  useEffect(() => {
    listAllOrders()
      .then((page) => {
        setOrders(page.results)
        setTotal(page.count)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const handleStatusChange = async (orderId: number, status: string) => {
    setUpdating(orderId)
    setActionError(null)
    try {
      const updated = await updateOrderStatus(orderId, status)
      setOrders((current) => current.map((o) => (o.id === orderId ? updated : o)))
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not update status')
    } finally {
      setUpdating(null)
    }
  }

  if (loading) return <p>Loading orders...</p>
  if (error) return <p className="error-message">Could not load orders: {error}</p>

  return (
    <div>
      <div className="page-header">
        <h1>Orders</h1>
        <span className="muted">
          {orders.length < total ? `Showing latest ${orders.length} of ${total}` : `${total} total`}
        </span>
      </div>
      {actionError && <p className="error-message">{actionError}</p>}

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Order</th>
              <th>Date</th>
              <th>Customer</th>
              <th>Payment</th>
              <th>Status</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <Fragment key={order.id}>
                <tr className="clickable-row" onClick={() => setExpanded(expanded === order.id ? null : order.id)}>
                  <td>#{order.id}</td>
                  <td>{formatDateTime(order.created_at)}</td>
                  <td>{order.full_name}</td>
                  <td>
                    <span className={`badge badge-${order.payment_status.toLowerCase()}`}>{order.payment_status}</span>
                  </td>
                  <td>
                    <span className={`badge badge-${order.status.toLowerCase()}`}>{order.status}</span>
                  </td>
                  <td>{formatPrice(order.total)}</td>
                </tr>
                {expanded === order.id && (
                  <tr className="order-details-row">
                    <td colSpan={6}>
                      <div className="order-details-content">
                        <div>
                          <strong>Items</strong>
                          <ul>
                            {order.items.map((item) => (
                              <li key={item.id}>
                                {item.name} × {item.quantity} — {formatPrice(item.line_total)}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <strong>Shipping</strong>
                          <p>
                            {order.address_line1}, {order.city}, {order.state} {order.postal_code}
                          </p>
                        </div>
                        <div onClick={(e) => e.stopPropagation()}>
                          <strong>Update status</strong>
                          {NEXT_STATUSES[order.status].length === 0 ? (
                            <p className="muted">This order is final.</p>
                          ) : (
                            <select
                              value=""
                              disabled={updating === order.id}
                              onChange={(e) => e.target.value && handleStatusChange(order.id, e.target.value)}
                            >
                              <option value="">Move to…</option>
                              {NEXT_STATUSES[order.status].map((status) => (
                                <option key={status} value={status}>
                                  {status}
                                </option>
                              ))}
                            </select>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default OrdersPage
