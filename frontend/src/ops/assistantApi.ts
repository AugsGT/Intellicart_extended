import { apiFetch } from '../api/client'
import type { Paginated } from '../types/common'

export interface OpsMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  payload: {
    table?: { columns: string[]; rows: (string | number)[][] }
    tools?: { name: string; arguments: Record<string, unknown> }[]
  }
  created_at: string
}

export interface OpsConversation {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface OpsConversationDetail extends OpsConversation {
  messages: OpsMessage[]
}

// Staff-only, read-only assistant. The server checks the role on every request.
export function listOpsConversations() {
  return apiFetch<Paginated<OpsConversation>>('/ops-assistant/conversations/?page_size=30')
}

export function createOpsConversation() {
  return apiFetch<OpsConversation>('/ops-assistant/conversations/', { method: 'POST', body: JSON.stringify({}) })
}

export function getOpsConversation(id: number) {
  return apiFetch<OpsConversationDetail>(`/ops-assistant/conversations/${id}/`)
}

export function deleteOpsConversation(id: number) {
  return apiFetch<void>(`/ops-assistant/conversations/${id}/`, { method: 'DELETE' })
}

export function askOps(id: number, text: string) {
  return apiFetch<{ message: OpsMessage }>(`/ops-assistant/conversations/${id}/messages/`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}
