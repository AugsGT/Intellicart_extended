import { apiFetch } from './client'
import type { Cart } from '../types/cart'

export function getCart() {
  return apiFetch<Cart>('/cart/')
}

export function addCartItem(productId: number, quantity = 1) {
  return apiFetch<Cart>('/cart/items/', {
    method: 'POST',
    body: JSON.stringify({ product_id: productId, quantity }),
  })
}

export function updateCartItem(itemId: number, quantity: number) {
  return apiFetch<Cart>(`/cart/items/${itemId}/`, {
    method: 'PATCH',
    body: JSON.stringify({ quantity }),
  })
}

export function removeCartItem(itemId: number) {
  return apiFetch<Cart>(`/cart/items/${itemId}/`, {
    method: 'DELETE',
  })
}

/** After login: move the anonymous (this browser's) cart into the user's cart. */
export function mergeCart() {
  return apiFetch<Cart>('/cart/merge/', { method: 'POST' })
}
