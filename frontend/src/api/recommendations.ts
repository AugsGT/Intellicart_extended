import { apiFetch } from './client'
import type { Product } from '../types/product'
import { FEATURES } from '../features'

export type RecommendationKind =
  | 'similar'
  | 'frequently_bought_together'
  | 'substitutes'
  | 'recently_viewed'
  | 'cart_based'
  | 'personalized'
  | 'advisor'

// Each product comes with a plain-language `reason` explaining why it was suggested.
function fetchList(path: string): Promise<Product[]> {
  if (!FEATURES.recommendations) return Promise.resolve([])
  return apiFetch<Product[]>(path)
}

export function getSimilarProducts(productId: number) {
  return fetchList(`/recommendations/products/${productId}/similar/`)
}

export function getFrequentlyBoughtTogether(productId: number) {
  return fetchList(`/recommendations/products/${productId}/frequently-bought-together/`)
}

export function getSubstitutes(productId: number) {
  return fetchList(`/recommendations/products/${productId}/substitutes/`)
}

export function getRecentlyViewed(excludeProductId?: number) {
  const query = excludeProductId ? `?exclude=${excludeProductId}` : ''
  return fetchList(`/recommendations/recently-viewed/${query}`)
}

export function getCartBasedRecommendations() {
  return fetchList('/recommendations/cart-based/')
}

export function getPersonalizedRecommendations() {
  return fetchList('/recommendations/personalized/')
}

/** Report that a recommended product was clicked. Failures are ignored: tracking must never get in the way. */
export function trackRecommendationClick(kind: RecommendationKind, productId: number) {
  if (!FEATURES.recommendations) return
  apiFetch('/recommendations/click/', {
    method: 'POST',
    body: JSON.stringify({ kind, product_id: productId }),
  }).catch(() => {})
}
