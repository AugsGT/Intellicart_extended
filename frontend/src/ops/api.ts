import { apiFetch, queryString } from '../api/client'
import type { Order } from '../types/cart'
import type { Paginated } from '../types/common'
import type {
  Alert, AuditAction, AuditEntry, BehaviourAnalytics, DeadLetter, DemandOverview, EventRecord, HighIntentCustomer, InventoryItem, Intervention, Overview,
  ProductDemand, ProductDemandDetail, RecommendationStat, SalesAnalytics, SalesSeries, StockMovement, SystemHealth,
} from './types'

// Operations endpoints. The server only answers ADMIN / OPERATIONS users
// (and ADMIN for restocking); the pages here just present the results.
const BIG_PAGE = 100

export function getOverview() {
  return apiFetch<Overview>('/analytics/overview/')
}

export function listAllOrders() {
  return apiFetch<Paginated<Order>>(`/orders/admin/all/${queryString({ page_size: BIG_PAGE })}`)
}

export function updateOrderStatus(orderId: number, status: string) {
  return apiFetch<Order>(`/orders/${orderId}/status/`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export function getInventory() {
  return apiFetch<Paginated<InventoryItem>>(`/inventory/${queryString({ page_size: BIG_PAGE })}`)
}

export function getStockHistory(productId: number) {
  return apiFetch<Paginated<StockMovement>>(`/inventory/${productId}/history/${queryString({ page_size: 50 })}`)
}

export function restockProduct(productId: number, quantity: number, note?: string) {
  return apiFetch<InventoryItem>(`/inventory/${productId}/restock/`, {
    method: 'POST',
    body: JSON.stringify({ quantity, note: note ?? '' }),
  })
}

export function getAlerts(resolved?: boolean) {
  return apiFetch<Paginated<Alert>>(`/alerts/${queryString({ resolved, page_size: BIG_PAGE })}`)
}

export function resolveAlert(alertId: number) {
  return apiFetch<Alert>(`/alerts/${alertId}/resolve/`, { method: 'PATCH' })
}

export function getEvents(eventType?: string) {
  return apiFetch<Paginated<EventRecord>>(`/events/${queryString({ event_type: eventType, page_size: BIG_PAGE })}`)
}

export function getDeadLetters() {
  return apiFetch<Paginated<DeadLetter>>('/events/dead-letters/?page_size=20')
}

export function getSystemHealth() {
  return apiFetch<SystemHealth>('/analytics/system/')
}

export function getInterventions() {
  return apiFetch<Paginated<Intervention>>(`/interventions/${queryString({ page_size: BIG_PAGE })}`)
}

export function getHighIntentCustomers() {
  return apiFetch<HighIntentCustomer[]>('/customer-intelligence/high-intent/')
}

export function getRecommendationStats() {
  return apiFetch<RecommendationStat[]>('/recommendations/stats/')
}

export function getDemandOverview() {
  return apiFetch<DemandOverview>('/demand/overview/')
}

export function getProductDemand() {
  return apiFetch<ProductDemand[]>('/demand/products/')
}

export function getProductDemandDetail(productId: number) {
  return apiFetch<ProductDemandDetail>(`/demand/products/${productId}/`)
}

export function getRestockRecommendations() {
  return apiFetch<ProductDemand[]>('/demand/restock/')
}

export function getSalesSeries(granularity: 'day' | 'week' | 'month') {
  return apiFetch<SalesSeries>(`/demand/sales/${queryString({ granularity })}`)
}

export function getBehaviourAnalytics() {
  return apiFetch<BehaviourAnalytics>('/analytics/products/')
}

export function getSalesAnalytics() {
  return apiFetch<SalesAnalytics>('/analytics/sales/')
}

export function getAuditLog(params: { action?: string; actor?: string; since?: string; until?: string; page?: number; page_size?: number }) {
  return apiFetch<Paginated<AuditEntry>>(`/audit/${queryString({ ...params })}`)
}

export function getAuditActions() {
  return apiFetch<AuditAction[]>('/audit/actions/')
}
