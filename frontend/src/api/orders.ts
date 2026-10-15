import { apiFetch } from './client'
import type { Order, PaymentMethod, PurchaseStats, ShippingAddress } from '../types/cart'
import type { Paginated } from '../types/common'

interface CreateOrderPayload extends ShippingAddress {
  payment_method: PaymentMethod
  card_number?: string
}

/** `idempotencyKey` makes the request safe to repeat: the server returns the first order instead of creating another. */
export function createOrder(address: ShippingAddress, paymentMethod: PaymentMethod, cardNumber?: string, idempotencyKey?: string) {
  const payload: CreateOrderPayload = {
    ...address,
    payment_method: paymentMethod,
    card_number: paymentMethod === 'card' ? cardNumber : undefined,
  }
  return apiFetch<Order>('/orders/', {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
  })
}

export function listOrders() {
  return apiFetch<Paginated<Order>>('/orders/')
}

export function getOrder(orderId: number | string) {
  return apiFetch<Order>(`/orders/${orderId}/`)
}

export function cancelOrder(orderId: number) {
  return apiFetch<Order>(`/orders/${orderId}/cancel/`, { method: 'POST' })
}

export function getPurchaseHistory() {
  return apiFetch<{ stats: PurchaseStats }>('/customer-intelligence/me/purchase-history/')
}
