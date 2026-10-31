import { apiFetch } from './client'
import { FEATURES } from '../features'

export interface ActiveIntervention {
  id: number
  action: string
  message: string
  signals: Record<string, unknown>
}

export function getActiveIntervention() {
  if (!FEATURES.interventions) return Promise.resolve(null)
  return apiFetch<ActiveIntervention | null>('/interventions/active/')
}

export function dismissIntervention(id: number) {
  return apiFetch<ActiveIntervention>(`/interventions/${id}/dismiss/`, { method: 'POST' })
}

/** The customer followed the message's button. */
export function clickIntervention(id: number) {
  return apiFetch<ActiveIntervention>(`/interventions/${id}/click/`, { method: 'POST' })
}
