import { getSessionId } from '../utils/session'
import { clearToken, getRefreshToken, getToken, setTokens } from '../utils/authToken'

export const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8001'

/** Fired when the session can no longer be refreshed, so the app can log the user out. */
export const SESSION_EXPIRED_EVENT = 'intellicart:session-expired'

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.status = status
    this.body = body
  }
}

/** Turns a Django REST Framework error body into one readable sentence. */
function messageFromBody(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object') return fallback
  const record = body as Record<string, unknown>
  if (typeof record.detail === 'string') return record.detail

  const parts: string[] = []
  for (const [field, value] of Object.entries(record)) {
    const text = Array.isArray(value) ? value.join(' ') : typeof value === 'string' ? value : null
    if (text) parts.push(field === 'non_field_errors' ? text : `${field}: ${text}`)
  }
  return parts.length > 0 ? parts.join(' ') : fallback
}

let refreshInFlight: Promise<boolean> | null = null

/** Gets a new access token using the refresh token. One refresh at a time. */
function refreshAccessToken(): Promise<boolean> {
  const refresh = getRefreshToken()
  if (!refresh) return Promise.resolve(false)

  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE_URL}/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
      .then(async (res) => {
        if (!res.ok) return false
        const data = await res.json()
        setTokens(data.access, data.refresh)
        return true
      })
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

async function send(path: string, options?: RequestInit): Promise<Response> {
  const token = getToken()
  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Session-Id': getSessionId(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  })
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  let res = await send(path, options)

  // Expired access token: refresh once and retry (never for the auth endpoints themselves).
  if (res.status === 401 && getToken() && !path.startsWith('/auth/')) {
    if (await refreshAccessToken()) {
      res = await send(path, options)
    } else {
      clearToken()
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(messageFromBody(body, `Request failed: ${res.status} ${res.statusText}`), res.status, body)
  }

  if (res.status === 204) {
    return undefined as T
  }

  return res.json()
}

/** Query string from an object, skipping empty values. */
export function queryString(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}
