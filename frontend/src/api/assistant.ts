import { apiFetch } from './client'
import type { Paginated } from '../types/common'
import type { ChatMessage, ConversationDetail, ConversationSummary, PendingAction, Understood } from '../types/assistant'

// The shopping advisor. Conversations belong to the logged-in customer.

export function listConversations() {
  return apiFetch<Paginated<ConversationSummary>>('/assistant/conversations/?page_size=20')
}

export function createConversation() {
  return apiFetch<ConversationSummary>('/assistant/conversations/', { method: 'POST', body: JSON.stringify({}) })
}

export function getConversation(id: number) {
  return apiFetch<ConversationDetail>(`/assistant/conversations/${id}/`)
}

export function deleteConversation(id: number) {
  return apiFetch<void>(`/assistant/conversations/${id}/`, { method: 'DELETE' })
}

export function sendMessage(id: number, text: string) {
  return apiFetch<{ message: ChatMessage; pending_action: PendingAction | null; understood: Understood }>(
    `/assistant/conversations/${id}/messages/`,
    { method: 'POST', body: JSON.stringify({ text }) },
  )
}

/** The customer's answer to "Shall I add this to your cart?" */
export function confirmAction(id: number, approve: boolean) {
  return apiFetch<{ message: ChatMessage; pending_action: PendingAction | null }>(`/assistant/conversations/${id}/confirm/`, {
    method: 'POST',
    body: JSON.stringify({ approve }),
  })
}
