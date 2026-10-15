import { apiFetch, queryString } from './client'
import type { Category, Product, ProductQuery } from '../types/product'
import type { Paginated } from '../types/common'

export function getProducts(query: ProductQuery = {}) {
  return apiFetch<Paginated<Product>>(`/products/${queryString({ ...query })}`)
}

export function getProduct(id: string | number) {
  return apiFetch<Product>(`/products/${id}/`)
}

export function getCategories() {
  return apiFetch<Category[]>('/categories/')
}
