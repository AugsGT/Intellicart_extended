import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getPurchaseHistory, listOrders } from '../api/orders'
import type { Order, PurchaseStats } from '../types/cart'
import { formatPrice } from '../utils/format'
import { useAuth } from '../context/AuthContext'
import './ProfilePage.css'

function ProfilePage() {
  const { user, loading: authLoading, logout } = useAuth()
  const navigate = useNavigate()
  const [orders, setOrders] = useState<Order[]>([])
  const [stats, setStats] = useState<PurchaseStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (authLoading) return
    if (!user) {
      setLoading(false)
      return
    }

    let cancelled = false
    Promise.all([listOrders(), getPurchaseHistory()])
      .then(([orderPage, history]) => {
        if (cancelled) return
        setOrders(orderPage.results)
        setStats(history.stats)
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
  }, [user, authLoading])

  const handleLogout = async () => {
    await logout()
    navigate('/')
  }

  return (
    <div className="profile-page">
      <h1>Profile</h1>

      {!authLoading && user && (
        <div className="account-card">
          <div>
            <span className="account-username">{user.username}</span>
            <span className="account-email">{user.email}</span>
          </div>
          <span className="account-role">{user.role}</span>
          <button type="button" className="logout-button" onClick={handleLogout}>
            Log out
          </button>
        </div>
      )}

      {!authLoading && !user && (
        <div className="account-card account-card-guest">
          <p>You are browsing as a guest. Log in to place orders and see your order history.</p>
          <div className="account-card-actions">
            <Link to="/login">Log in</Link>
            <Link to="/register">Register</Link>
          </div>
        </div>
      )}

      {user && stats && stats.order_count > 0 && (
        <div className="purchase-stats">
          <div>
            <strong>{stats.order_count}</strong>
            <span>orders</span>
          </div>
          <div>
            <strong>{formatPrice(stats.total_spent)}</strong>
            <span>total spent</span>
          </div>
          <div>
            <strong>{stats.items_purchased}</strong>
            <span>items bought</span>
          </div>
          {stats.top_products[0] && (
            <div>
              <strong>{stats.top_products[0].name}</strong>
              <span>most bought</span>
            </div>
          )}
        </div>
      )}

      {user && (
        <>
          <h2>Order History</h2>
          {loading && <p>Loading orders...</p>}
          {error && <p className="error-message">Could not load your orders: {error}</p>}
          {!loading && !error && orders.length === 0 && (
            <p>
              No orders yet. <Link to="/">Start shopping →</Link>
            </p>
          )}

          {!loading && !error && orders.length > 0 && (
            <ul className="order-history-list">
              {orders.map((order) => (
                <li key={order.id}>
                  <Link to={`/orders/${order.id}`} className="order-history-row">
                    <div>
                      <span className="order-id">Order #{order.id}</span>
                      <span className="order-date">{new Date(order.created_at).toLocaleDateString()}</span>
                    </div>
                    <span className="order-item-count">
                      {order.items.reduce((sum, item) => sum + item.quantity, 0)} item(s)
                    </span>
                    {(order.status === 'FAILED' || order.status === 'CANCELLED') && (
                      <span className="order-status-failed">{order.status === 'FAILED' ? 'Failed' : 'Cancelled'}</span>
                    )}
                    <span className="order-total">{formatPrice(order.total)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

export default ProfilePage
