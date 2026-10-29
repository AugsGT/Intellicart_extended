import { useEffect, useState } from 'react'
import { getEvents } from '../api'
import type { EventRecord } from '../types'
import { formatDateTime } from '../../utils/format'

const EVENT_TYPES = [
  'PRODUCT_VIEWED', 'PRODUCT_SEARCHED',
  'CART_ITEM_ADDED', 'CART_ITEM_REMOVED', 'CART_ABANDONED',
  'CHECKOUT_STARTED', 'ORDER_CREATED', 'ORDER_COMPLETED', 'ORDER_CANCELLED',
  'PAYMENT_SUCCEEDED', 'PAYMENT_FAILED',
  'INVENTORY_UPDATED', 'STOCK_LOW', 'STOCK_RESTOCKED',
  'RECOMMENDATION_GENERATED', 'RECOMMENDATION_CLICKED', 'RECOMMENDATION_PURCHASED',
  'DEMAND_SPIKE_DETECTED',
]

function EventsPage() {
  const [events, setEvents] = useState<EventRecord[]>([])
  const [total, setTotal] = useState(0)
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getEvents(filter || undefined)
      .then((page) => {
        if (cancelled) return
        setEvents(page.results)
        setTotal(page.count)
        setError(null)
      })
      .catch((err: Error) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [filter])

  return (
    <div>
      <div className="page-header">
        <h1>Events</h1>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Event type">
          <option value="">All event types</option>
          {EVENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>
      <p className="muted">
        Events that have been through the queue and consumer. {total > events.length ? `Showing latest ${events.length} of ${total}.` : `${total} total.`}
      </p>

      {loading && <p>Loading events...</p>}
      {error && <p className="error-message">Could not load events: {error}</p>}

      {!loading && !error && (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>User</th>
                <th>Session</th>
                <th>Entity</th>
                <th>Payload</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td>
                    <span className="badge badge-confirmed">{event.event_type}</span>
                  </td>
                  <td>{event.user_id ?? <span className="muted">guest</span>}</td>
                  <td className="muted">{event.session_id ? event.session_id.slice(0, 8) : '-'}</td>
                  <td>{event.entity_id ?? '-'}</td>
                  <td className="muted small">{JSON.stringify(event.payload)}</td>
                  <td>{formatDateTime(event.occurred_at)}</td>
                </tr>
              ))}
              {events.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    No events yet. Is the event consumer running?
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default EventsPage
