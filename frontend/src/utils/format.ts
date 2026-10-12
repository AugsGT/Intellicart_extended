import type { StockStatus } from '../types/product'

export function formatPrice(price: string | number): string {
  const value = typeof price === 'string' ? parseFloat(price) : price
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString()
}

// The backend decides healthy / low / out of stock (it knows each product's threshold).
export function getStockStatus(stock: number, status: StockStatus): { label: string; className: string } {
  if (status === 'out_of_stock') return { label: 'Out of stock', className: 'stock-out' }
  if (status === 'low_stock') return { label: `Low stock (${stock} left)`, className: 'stock-low' }
  return { label: `In stock (${stock})`, className: 'stock-ok' }
}
