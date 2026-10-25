export interface ProductAttribute {
  key: string
  label: string
  value: string | number
  unit: string
}

export type StockStatus = 'healthy' | 'low_stock' | 'out_of_stock'

export interface Product {
  id: number
  name: string
  description: string
  price: string
  category: number
  category_name: string
  brand: string
  image: string
  stock: number
  low_stock_threshold: number
  stock_status: StockStatus
  status: string
  attributes: ProductAttribute[]
  /** Why this was recommended (only on recommendation results). */
  reason?: string
  created_at: string
  updated_at: string
}

export interface Category {
  id: number
  name: string
  slug: string
  parent: number | null
}

export interface ProductQuery {
  q?: string
  category?: number | string
  ordering?: string
  page?: number
  page_size?: number
}
