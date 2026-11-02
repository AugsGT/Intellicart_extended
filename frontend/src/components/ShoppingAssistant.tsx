import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  confirmAction,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  sendMessage,
} from '../api/assistant'
import { useAuth } from '../context/AuthContext'
import { useCart } from '../context/CartContext'
import type { AdvisorCard, ChatMessage, ConversationSummary, PendingAction, Understood } from '../types/assistant'
import { AdvisorCards, ComparisonTable } from './AdvisorCards'
import './ShoppingAssistant.css'

const SUGGESTED_PROMPTS = [
  'My budget is ₹60,000. I need a laptop for programming with good battery life and a reliable warranty.',
  'I need wireless earbuds under ₹3,000 with good noise cancellation.',
  'Suggest a durable office chair under ₹10,000.',
  'Find a phone with a good camera and good battery life.',
]

const WELCOME: ChatMessage = {
  id: 0,
  role: 'assistant',
  content: 'Hi! Tell me what you need (product, budget, what matters most) and I will find options from our catalogue.',
  payload: {},
  created_at: '',
}

function ShoppingAssistant() {
  const { user, loading: authLoading } = useAuth()
  const { refresh: refreshCart } = useCart()

  const [open, setOpen] = useState(false)
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [understood, setUnderstood] = useState<Understood | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight })
  }, [messages, pending, open, sending])

  const openConversation = async (id: number) => {
    setLoading(true)
    setError(null)
    try {
      const detail = await getConversation(id)
      setActiveId(id)
      setMessages(detail.messages)
      setPending(detail.pending_action)
      setUnderstood(detail.understood)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the conversation')
    } finally {
      setLoading(false)
    }
  }

  // When the panel opens for a logged-in customer, show their most recent conversation.
  useEffect(() => {
    if (!open || !user) return
    let cancelled = false
    listConversations()
      .then((page) => {
        if (cancelled) return
        setConversations(page.results)
        if (activeId === null && page.results.length > 0) openConversation(page.results[0].id)
      })
      .catch((err: Error) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user?.id])

  // A different customer logging in must not see the previous one's chat.
  useEffect(() => {
    setActiveId(null)
    setMessages([])
    setPending(null)
    setUnderstood(null)
    setConversations([])
  }, [user?.id])

  const startNew = () => {
    setActiveId(null)
    setMessages([])
    setPending(null)
    setUnderstood(null)
    setError(null)
  }

  const send = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || sending) return
    setSending(true)
    setError(null)
    setInput('')

    try {
      let id = activeId
      if (id === null) {
        const created = await createConversation()
        id = created.id
        setActiveId(id)
      }
      setMessages((current) => [
        ...current,
        { id: -Date.now(), role: 'user', content: trimmed, payload: {}, created_at: '' },
      ])
      const result = await sendMessage(id, trimmed)
      setMessages((current) => [...current, result.message])
      setPending(result.pending_action)
      setUnderstood(result.understood)
      listConversations().then((page) => setConversations(page.results)).catch(() => {})
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reach the advisor')
    } finally {
      setSending(false)
    }
  }

  const answerPending = async (approve: boolean) => {
    if (activeId === null || sending) return
    setSending(true)
    setError(null)
    try {
      const result = await confirmAction(activeId, approve)
      setMessages((current) => [...current, result.message])
      setPending(result.pending_action)
      if (result.message.payload.cart) await refreshCart()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not complete that')
    } finally {
      setSending(false)
    }
  }

  const handleDelete = async () => {
    if (activeId === null || !window.confirm('Delete this conversation?')) return
    try {
      await deleteConversation(activeId)
      setConversations((current) => current.filter((c) => c.id !== activeId))
      startNew()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete the conversation')
    }
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    send(input)
  }

  const askToAdd = (card: AdvisorCard) => send(`Add the ${card.name} to my cart`)

  const shown = messages.length > 0 ? messages : [WELCOME]

  return (
    <div className="assistant-root">
      {open && (
        <div className="assistant-panel" role="dialog" aria-label="Shopping advisor">
          <div className="assistant-header">
            <span>Shopping Advisor</span>
            <button type="button" className="assistant-close" onClick={() => setOpen(false)} aria-label="Close">
              ✕
            </button>
          </div>

          {!authLoading && !user && (
            <div className="assistant-body">
              <div className="assistant-bubble assistant">
                Please <Link to="/login">log in</Link> to chat with the shopping advisor. Your conversations are saved to your account.
              </div>
            </div>
          )}

          {user && (
            <>
              <div className="assistant-toolbar">
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
                <button type="button" onClick={startNew}>
                  New
                </button>
                {activeId !== null && (
                  <button type="button" onClick={handleDelete} aria-label="Delete conversation">
                    🗑
                  </button>
                )}
              </div>

              {understood?.summary && (
                <div className="assistant-understood">
                  Looking for: <strong>{understood.summary}</strong>
                  {understood.priorities.length > 0 && <> · priorities: {understood.priorities.join(', ')}</>}
                </div>
              )}

              <div className="assistant-body" ref={bodyRef}>
                {loading && <p className="assistant-note">Loading conversation…</p>}
                {shown.map((m, index) => (
                  <div key={m.id || `w${index}`} className={`assistant-turn ${m.role}`}>
                    <div className={`assistant-bubble ${m.role}`}>{m.content}</div>
                    {m.payload.cards && m.payload.cards.length > 0 && (
                      <AdvisorCards cards={m.payload.cards} onAskToAdd={askToAdd} disabled={sending} />
                    )}
                    {m.payload.comparison && <ComparisonTable comparison={m.payload.comparison} />}
                    {m.payload.cart && (
                      <Link to={m.payload.cart.link} className="assistant-cart-link">
                        View cart ({m.payload.cart.item_count} item{m.payload.cart.item_count === 1 ? '' : 's'}) →
                      </Link>
                    )}
                  </div>
                ))}

                {messages.length === 0 && !loading && (
                  <div className="assistant-suggestions">
                    {SUGGESTED_PROMPTS.map((prompt) => (
                      <button key={prompt} type="button" onClick={() => send(prompt)} disabled={sending}>
                        {prompt}
                      </button>
                    ))}
                  </div>
                )}

                {pending && (
                  <div className="assistant-confirm" role="alert">
                    <p>{pending.summary}?</p>
                    <div>
                      <button type="button" className="confirm-yes" onClick={() => answerPending(true)} disabled={sending}>
                        Confirm
                      </button>
                      <button type="button" onClick={() => answerPending(false)} disabled={sending}>
                        Cancel
                      </button>
                    </div>
                    <small>Nothing is added until you confirm. The advisor never places orders or takes payment.</small>
                  </div>
                )}

                {sending && <div className="assistant-bubble assistant typing">Thinking…</div>}
                {error && <p className="assistant-error">{error}</p>}
              </div>

              <form className="assistant-input-row" onSubmit={handleSubmit}>
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="e.g. laptop under 60000 for coding"
                  disabled={sending}
                  maxLength={1000}
                />
                <button type="submit" disabled={sending || !input.trim()}>
                  Send
                </button>
              </form>
            </>
          )}
        </div>
      )}

      <button
        type="button"
        className="assistant-toggle"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Close shopping advisor' : 'Open shopping advisor'}
      >
        {open ? '✕' : '💬'}
      </button>
    </div>
  )
}

export default ShoppingAssistant
