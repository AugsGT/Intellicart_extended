import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  askOps,
  createOpsConversation,
  deleteOpsConversation,
  getOpsConversation,
  listOpsConversations,
  type OpsConversation,
  type OpsMessage,
} from '../assistantApi'

const SUGGESTED_QUESTIONS = [
  'What operational issues need attention?',
  'Which products have experienced a sudden demand increase?',
  'Which products are likely to run out of stock?',
  'Which products need restocking?',
  'Which products have declining sales?',
  'What are the top-selling products?',
  'How has demand changed over the last 30 days?',
  'Which products have unusual sales patterns?',
  'Why has inventory decreased?',
  'What is our current cancellation rate?',
]

function AssistantPage() {
  const [conversations, setConversations] = useState<OpsConversation[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<OpsMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listOpsConversations()
      .then((page) => setConversations(page.results))
      .catch((err: Error) => setError(err.message))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, sending])

  const openConversation = async (id: number) => {
    setLoading(true)
    setError(null)
    try {
      const detail = await getOpsConversation(id)
      setActiveId(id)
      setMessages(detail.messages)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the conversation')
    } finally {
      setLoading(false)
    }
  }

  const startNew = () => {
    setActiveId(null)
    setMessages([])
    setError(null)
  }

  const ask = async (text: string) => {
    const question = text.trim()
    if (!question || sending) return
    setSending(true)
    setError(null)
    setInput('')
    try {
      let id = activeId
      if (id === null) {
        const created = await createOpsConversation()
        id = created.id
        setActiveId(id)
      }
      setMessages((current) => [...current, { id: -Date.now(), role: 'user', content: question, payload: {}, created_at: '' }])
      const result = await askOps(id, question)
      setMessages((current) => [...current, result.message])
      listOpsConversations().then((page) => setConversations(page.results)).catch(() => {})
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not get an answer')
    } finally {
      setSending(false)
    }
  }

  const handleDelete = async () => {
    if (activeId === null || !window.confirm('Delete this conversation?')) return
    try {
      await deleteOpsConversation(activeId)
      setConversations((current) => current.filter((c) => c.id !== activeId))
      startNew()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete the conversation')
    }
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    ask(input)
  }

  return (
    <div className="ops-assistant">
      <div className="page-header">
        <h1>Operations Assistant</h1>
        <div className="ops-assistant-controls">
          <select
            value={activeId ?? ''}
            onChange={(e) => (e.target.value ? openConversation(Number(e.target.value)) : startNew())}
            aria-label="Conversation history"
          >
            <option value="">New conversation</option>
            {conversations.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title || `Conversation ${c.id}`}
              </option>
            ))}
          </select>
          {activeId !== null && (
            <button type="button" className="btn" onClick={handleDelete}>
              Delete
            </button>
          )}
        </div>
      </div>

      <p className="muted small">
        Read-only: I answer from live order, stock, demand and system data, and every figure comes from a tool I ran (shown under each answer).
        I cannot change orders, stock or settings.
      </p>

      <div className="panel ops-chat">
        <div className="ops-chat-body">
          {loading && <p className="muted">Loading conversation…</p>}

          {messages.length === 0 && !loading && (
            <div className="ops-suggestions">
              <p className="muted">Try one of these:</p>
              {SUGGESTED_QUESTIONS.map((question) => (
                <button key={question} type="button" onClick={() => ask(question)} disabled={sending}>
                  {question}
                </button>
              ))}
            </div>
          )}

          {messages.map((message) => (
            <div key={message.id} className={`ops-turn ${message.role}`}>
              <div className={`ops-bubble ${message.role}`}>{message.content}</div>

              {message.payload.table && (
                <div className="ops-answer-table">
                  <table>
                    <thead>
                      <tr>
                        {message.payload.table.columns.map((column) => (
                          <th key={column}>{column}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {message.payload.table.rows.map((row, index) => (
                        <tr key={index}>
                          {row.map((cell, cellIndex) => (
                            <td key={cellIndex}>{cell}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {message.payload.tools && message.payload.tools.length > 0 && (
                <details className="ops-tools-used">
                  <summary>Data used ({message.payload.tools.length})</summary>
                  <ul>
                    {message.payload.tools.map((tool, index) => (
                      <li key={index}>
                        <code>{tool.name}</code>
                        {Object.keys(tool.arguments).length > 0 && <> {JSON.stringify(tool.arguments)}</>}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ))}

          {sending && <div className="ops-bubble assistant typing">Looking at the data…</div>}
          {error && <p className="error-message">{error}</p>}
          <div ref={bottomRef} />
        </div>

        <form className="ops-chat-input" onSubmit={handleSubmit}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about demand, stock, orders, alerts or system health…"
            disabled={sending}
            maxLength={1000}
          />
          <button type="submit" className="btn btn-primary" disabled={sending || !input.trim()}>
            Ask
          </button>
        </form>
      </div>
    </div>
  )
}

export default AssistantPage
