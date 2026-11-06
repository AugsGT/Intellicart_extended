import { afterEach, describe, expect, it, vi } from 'vitest'
import { createOrder } from './orders'
import { newIdempotencyKey } from '../utils/idempotency'

const ADDRESS = { full_name: 'A', address_line1: 'B', city: 'C', state: 'D', postal_code: '560001', phone: '9999999999' }

function capture() {
  const calls: { init: RequestInit }[] = []
  vi.stubGlobal('crypto', { randomUUID: () => 'abc-123' })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init: RequestInit) => {
      calls.push({ init })
      return { ok: true, status: 201, json: async () => ({ id: 1 }) } as Response
    }),
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('createOrder', () => {
  it('sends the idempotency key so a repeat cannot create a second order', async () => {
    const calls = capture()
    await createOrder(ADDRESS, 'cod', undefined, 'key-42')
    expect((calls[0].init.headers as Record<string, string>)['Idempotency-Key']).toBe('key-42')
  })

  it('works without a key', async () => {
    const calls = capture()
    await createOrder(ADDRESS, 'cod')
    expect((calls[0].init.headers as Record<string, string>)['Idempotency-Key']).toBeUndefined()
  })

  it('only sends a card number for card payments', async () => {
    const calls = capture()
    await createOrder(ADDRESS, 'upi', '4242424242424242')
    await createOrder(ADDRESS, 'card', '4242424242424242')
    expect(JSON.parse(calls[0].init.body as string).card_number).toBeUndefined()
    expect(JSON.parse(calls[1].init.body as string).card_number).toBe('4242424242424242')
  })
})

describe('newIdempotencyKey', () => {
  it('produces something the server accepts (1-64 letters, digits, dash, underscore)', () => {
    vi.stubGlobal('crypto', { randomUUID: () => '3f2b8c1e-9d4a-4e6f-8a1b-0c5d7e9f2a34' })
    expect(newIdempotencyKey()).toMatch(/^[A-Za-z0-9_-]{1,64}$/)
    vi.unstubAllGlobals()
  })
})
