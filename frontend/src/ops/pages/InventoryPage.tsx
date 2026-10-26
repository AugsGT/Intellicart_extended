import { Fragment, useEffect, useState } from 'react'
import { getInventory, getStockHistory, restockProduct } from '../api'
import { useAuth } from '../../context/AuthContext'
import type { InventoryItem, StockMovement } from '../types'
import { formatDateTime } from '../../utils/format'

function InventoryPage() {
  const { user } = useAuth()
  const canRestock = user?.role === 'ADMIN' // the server allows restocking for ADMIN only

  const [items, setItems] = useState<InventoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [history, setHistory] = useState<StockMovement[]>([])
  const [restockQty, setRestockQty] = useState('')
  const [restocking, setRestocking] = useState(false)

  const load = () => {
    getInventory()
      .then((page) => setItems(page.results))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const toggleExpand = (productId: number) => {
    if (expanded === productId) {
      setExpanded(null)
      return
    }
    setExpanded(productId)
    setRestockQty('')
    setActionError(null)
    getStockHistory(productId)
      .then((page) => setHistory(page.results))
      .catch(() => setHistory([]))
  }

  const handleRestock = async (productId: number) => {
    const quantity = parseInt(restockQty, 10)
    if (!quantity || quantity <= 0) return
    setRestocking(true)
    setActionError(null)
    try {
      await restockProduct(productId, quantity)
      load()
      setHistory((await getStockHistory(productId)).results)
      setRestockQty('')
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not restock')
    } finally {
      setRestocking(false)
    }
  }

  if (loading) return <p>Loading inventory...</p>
  if (error) return <p className="error-message">Could not load inventory: {error}</p>

  return (
    <div>
      <div className="page-header">
        <h1>Inventory</h1>
        <span className="muted">{items.length} products</span>
      </div>

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>Stock</th>
              <th>Threshold</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <Fragment key={item.product_id}>
                <tr className="clickable-row" onClick={() => toggleExpand(item.product_id)}>
                  <td>{item.name}</td>
                  <td>{item.stock}</td>
                  <td>{item.low_stock_threshold}</td>
                  <td>
                    <span className={`badge badge-${item.status}`}>{item.status.replace('_', ' ')}</span>
                  </td>
                  <td>{expanded === item.product_id ? '▲' : '▼'}</td>
                </tr>
                {expanded === item.product_id && (
                  <tr className="order-details-row">
                    <td colSpan={5}>
                      <div className="inventory-detail" onClick={(e) => e.stopPropagation()}>
                        <div className="restock-form">
                          <strong>Restock</strong>
                          {canRestock ? (
                            <div className="restock-inputs">
                              <input
                                type="number"
                                min={1}
                                placeholder="Quantity"
                                value={restockQty}
                                onChange={(e) => setRestockQty(e.target.value)}
                              />
                              <button
                                type="button"
                                className="btn btn-primary"
                                disabled={restocking}
                                onClick={() => handleRestock(item.product_id)}
                              >
                                {restocking ? 'Restocking...' : 'Add Stock'}
                              </button>
                            </div>
                          ) : (
                            <p className="muted">Only administrators can add stock.</p>
                          )}
                          {actionError && <p className="error-message">{actionError}</p>}
                        </div>

                        <div className="movement-history">
                          <strong>Movement History</strong>
                          {history.length === 0 ? (
                            <p className="muted">No movements recorded yet.</p>
                          ) : (
                            <table className="history-table">
                              <tbody>
                                {history.map((m) => (
                                  <tr key={m.id}>
                                    <td>{formatDateTime(m.created_at)}</td>
                                    <td>{m.reason}</td>
                                    <td className={m.change >= 0 ? 'positive' : 'negative'}>
                                      {m.change >= 0 ? '+' : ''}
                                      {m.change}
                                    </td>
                                    <td>→ {m.resulting_stock}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
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

export default InventoryPage
