import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, SESSION_EXPIRED_EVENT, apiFetch, queryString } from './client'
import { getRefreshToken, getToken, setTokens } from '../utils/authToken'

type Reply = { status?: number; body?: unknown }

/** Replaces fetch with a script of replies, and records every request. */
function mockFetch(...replies: Reply[]) {
  const calls: { url: string; init: RequestInit }[] = []
  const queue = [...replies]
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      const reply = queue.shift() ?? { status: 200, body: {} }
      const status = reply.status ?? 200
      return {
        ok: status >= 200 && status < 300,
        status,
        statusText: 'status',
        json: async () => {
          if (reply.body === undefined) throw new Error('no body')
          return reply.body
        },
      } as Response
    }),
  )
  return calls
}

const headersOf = (call: { init: RequestInit }) => call.init.headers as Record<string, string>

beforeEach(() => {
  vi.stubGlobal('crypto', { randomUUID: () => 'session-abc' })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiFetch basics', () => {
  it('returns the parsed JSON and always sends the browser session id', async () => {
    const calls = mockFetch({ body: { hello: 'world' } })
    expect(await apiFetch('/products/')).toEqual({ hello: 'world' })
    expect(calls[0].url).toMatch(/\/products\/$/)
    expect(headersOf(calls[0])['X-Session-Id']).toBe('session-abc')
    expect(headersOf(calls[0]).Authorization).toBeUndefined()   // no token, no header
  })

  it('sends the access token when logged in', async () => {
    setTokens('access-1', 'refresh-1')
    const calls = mockFetch({ body: {} })
    await apiFetch('/users/me/')
    expect(headersOf(calls[0]).Authorization).toBe('Bearer access-1')
  })

  it('returns nothing for a 204', async () => {
    mockFetch({ status: 204 })
    expect(await apiFetch('/products/1/', { method: 'DELETE' })).toBeUndefined()
  })

  it('lets a caller add headers (the checkout idempotency key)', async () => {
    const calls = mockFetch({ body: {} })
    await apiFetch('/orders/', { method: 'POST', headers: { 'Idempotency-Key': 'key-1' } })
    expect(headersOf(calls[0])['Idempotency-Key']).toBe('key-1')
    expect(headersOf(calls[0])['Content-Type']).toBe('application/json')
  })
})

describe('error messages', () => {
  async function failure(body: unknown, status = 400): Promise<ApiError> {
    mockFetch({ status, body })
    try {
      await apiFetch('/x/')
    } catch (err) {
      return err as ApiError
    }
    throw new Error('the request should have failed')
  }

  it('uses the detail message', async () => {
    const error = await failure({ detail: 'Cart is empty' })
    expect(error).toBeInstanceOf(ApiError)
    expect(error.message).toBe('Cart is empty')
    expect(error.status).toBe(400)
  })

  it('turns field errors into one readable sentence', async () => {
    const error = await failure({ email: ['Email already exists'], password: ['Too short.', 'Too common.'] })
    expect(error.message).toBe('email: Email already exists password: Too short. Too common.')
  })

  it('shows non-field errors without a field name', async () => {
    expect((await failure({ non_field_errors: ['Choose a payment method'] })).message).toBe('Choose a payment method')
  })

  it('falls back to the status when the body is not JSON', async () => {
    mockFetch({ status: 502 })
    let error: ApiError | undefined
    try {
      await apiFetch('/x/')
    } catch (err) {
      error = err as ApiError
    }
    expect(error?.message).toContain('502')
  })

  it('keeps the response body, so the checkout can read the failed order of a declined card', async () => {
    const error = await failure({ detail: 'Payment was declined', order: { id: 7 } }, 402)
    expect(error.status).toBe(402)
    expect((error.body as { order: { id: number } }).order.id).toBe(7)
  })
})

describe('refreshing an expired login', () => {
  it('refreshes once, stores the new tokens, and retries the request', async () => {
    setTokens('old-access', 'refresh-1')
    const calls = mockFetch(
      { status: 401, body: { detail: 'expired' } },
      { body: { access: 'new-access', refresh: 'refresh-2' } },
      { body: { ok: true } },
    )
    expect(await apiFetch('/orders/')).toEqual({ ok: true })
    expect(calls.map((c) => c.url.replace(/^.*localhost:\d+/, ''))).toEqual(['/orders/', '/auth/refresh/', '/orders/'])
    expect(headersOf(calls[2]).Authorization).toBe('Bearer new-access')
    expect(getToken()).toBe('new-access')
    expect(getRefreshToken()).toBe('refresh-2')                   // refresh tokens rotate
  })

  it('logs the user out when the refresh token no longer works', async () => {
    setTokens('old-access', 'dead-refresh')
    mockFetch({ status: 401, body: { detail: 'expired' } }, { status: 401, body: { detail: 'bad refresh' } })
    const expired = vi.fn()
    window.addEventListener(SESSION_EXPIRED_EVENT, expired)

    await expect(apiFetch('/orders/')).rejects.toBeInstanceOf(ApiError)
    expect(getToken()).toBeNull()
    expect(expired).toHaveBeenCalledOnce()
    window.removeEventListener(SESSION_EXPIRED_EVENT, expired)
  })

  it('does not try to refresh a failed login attempt', async () => {
    setTokens('some-access', 'refresh-1')
    const calls = mockFetch({ status: 401, body: { detail: 'Invalid email or password' } })
    await expect(apiFetch('/auth/login/', { method: 'POST' })).rejects.toThrow('Invalid email or password')
    expect(calls).toHaveLength(1)
  })

  it('does not refresh for guests', async () => {
    const calls = mockFetch({ status: 401, body: { detail: 'no' } })
    await expect(apiFetch('/users/me/')).rejects.toBeInstanceOf(ApiError)
    expect(calls).toHaveLength(1)
  })

  it('shares one refresh between simultaneous requests', async () => {
    setTokens('old', 'refresh-1')
    const calls = mockFetch(
      { status: 401, body: {} }, { status: 401, body: {} },        // both requests expire together
      { body: { access: 'fresh', refresh: 'refresh-2' } },         // ONE refresh
      { body: { n: 1 } }, { body: { n: 2 } },
    )
    const results = await Promise.all([apiFetch('/a/'), apiFetch('/b/')])
    expect(results).toHaveLength(2)
    expect(calls.filter((c) => c.url.includes('/auth/refresh/'))).toHaveLength(1)
  })
})

describe('queryString', () => {
  it('skips empty values and encodes the rest', () => {
    expect(queryString({ q: 'red lamp', page: 2, category: '', min: undefined, flag: false })).toBe('?q=red+lamp&page=2&flag=false')
    expect(queryString({})).toBe('')
  })
})
