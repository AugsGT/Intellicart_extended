import { apiFetch } from './client'
import { FEATURES } from '../features'

export function trackCheckoutStarted() {
  if (!FEATURES.eventTracking) return Promise.resolve({ detail: 'skipped' })
  return apiFetch<{ detail: string }>('/events/checkout-started/', { method: 'POST' })
}
