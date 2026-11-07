import { describe, expect, it } from 'vitest'
import { formatPrice, getStockStatus } from './format'

describe('formatPrice', () => {
  it('uses rupees with Indian digit grouping', () => {
    expect(formatPrice('1499.00').replace(/\s/g, '')).toBe('₹1,499.00')
    expect(formatPrice(5000000).replace(/\s/g, '')).toBe('₹50,00,000.00')
  })

  it('accepts strings from the API and numbers', () => {
    expect(formatPrice('0')).toBe(formatPrice(0))
  })
})

describe('getStockStatus', () => {
  it('follows the status the server computed (it knows each product threshold)', () => {
    expect(getStockStatus(0, 'out_of_stock')).toEqual({ label: 'Out of stock', className: 'stock-out' })
    expect(getStockStatus(4, 'low_stock')).toEqual({ label: 'Low stock (4 left)', className: 'stock-low' })
    expect(getStockStatus(40, 'healthy')).toEqual({ label: 'In stock (40)', className: 'stock-ok' })
  })
})
