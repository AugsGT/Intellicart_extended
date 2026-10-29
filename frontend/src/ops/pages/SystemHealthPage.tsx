import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../../api/client'
import { getDeadLetters, getSystemHealth } from '../api'
import type { DeadLetter, QueueDepth, SystemHealth } from '../types'
import StatCard from '../StatCard'
import { formatDateTime } from '../../utils/format'

function formatAge(seconds: number | null): string {
  if (seconds === null) return 'none waiting'
  if (seconds < 60) return `${seconds} s`
  return `${Math.round(seconds / 60)} min`
}

function QueueLine({ label, queue }: { label: string; queue: QueueDepth | null }) {
  return (
    <li>
      <span>{label}</span>
      {queue ? (
        <span className="muted small">
          {queue.messages_ready} waiting · {queue.messages_unacked} in progress · {queue.consumers} consumer(s)
        </span>
      ) : (
        <span className="muted small">not available (RabbitMQ management API not configured)</span>
      )}
    </li>
  )
}

function SystemHealthPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [deadLetters, setDeadLetters] = useState<DeadLetter[]>([])
  const [database, setDatabase] = useState('checking...')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getSystemHealth(), getDeadLetters()])
      .then(([healthData, deadPage]) => {
        setHealth(healthData)
        setDeadLetters(deadPage.results.filter((d) => !d.resolved_at))
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))

    fetch(`${API_BASE_URL}/health/`)
      .then((res) => res.json())
      .then((data) => setDatabase(data.database))
      .catch(() => setDatabase('unreachable'))
  }, [])

  if (loading) return <p>Loading system health...</p>
  if (error) return <p className="error-message">Could not load system health: {error}</p>
  if (!health) return null

  const outboxBacklog = health.outbox_pending > 0 && (health.outbox_oldest_pending_seconds ?? 0) > 30

  return (
    <div>
      <div className="page-header">
        <h1>System Health</h1>
      </div>

      <div className="stats-grid">
        <StatCard label="Database" value={database} accent={database === 'up' ? 'default' : 'danger'} />
        <StatCard
          label="Outbox waiting"
          value={health.outbox_pending}
          accent={outboxBacklog || health.outbox_failing > 0 ? 'danger' : 'default'}
        />
        <StatCard label="Oldest waiting" value={formatAge(health.outbox_oldest_pending_seconds)} />
        <StatCard label="Events (last hour)" value={health.events_last_hour} />
        <StatCard
          label="Dead letters"
          value={health.dead_letters_unresolved}
          accent={health.dead_letters_unresolved > 0 ? 'danger' : 'default'}
        />
      </div>

      <div className="overview-columns">
        <div className="panel">
          <h2>Event pipeline</h2>
          <ul className="simple-list">
            <li>
              <span>Last event processed</span>
              <span className="muted small">
                {health.last_event_processed_at ? formatDateTime(health.last_event_processed_at) : 'never'}
              </span>
            </li>
            <li>
              <span>Outbox events failing to send</span>
              <span className="muted small">{health.outbox_failing}</span>
            </li>
            <QueueLine label="Event queue" queue={health.queue} />
            <QueueLine label="Dead-letter queue" queue={health.dead_letter_queue} />
          </ul>
          <p className="muted small">
            Waiting events are sent by the relay (Celery beat or <code>manage.py relay_outbox --loop</code>); consumed
            by <code>manage.py run_event_consumer</code>.
          </p>
        </div>

        <div className="panel">
          <h2>Unresolved dead letters</h2>
          {deadLetters.length === 0 ? (
            <p className="muted">None. Every event was processed.</p>
          ) : (
            <ul className="simple-list">
              {deadLetters.map((dead) => (
                <li key={dead.id}>
                  <span className="badge badge-high">{dead.event_type || 'invalid'}</span>
                  <span>{dead.error}</span>
                  <span className="muted small">{formatDateTime(dead.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

export default SystemHealthPage
