export interface CartItem {
  id: number
  product_id: number
  name: string
  price: string
  image: string
  stock: number
  quantity: number
  line_total: string
}

export interface Cart {
  id: number
  items: CartItem[]
  subtotal: string
  tax: string
  shipping: string
  total: string
}

export interface ShippingAddress {
  full_name: string
  address_line1: string
  city: string
  state: string
  postal_code: string
  phone: string
}

export type PaymentMethod = 'card' | 'upi' | 'cod'

export type OrderStatus = 'CONFIRMED' | 'SHIPPED' | 'DELIVERED' | 'CANCELLED' | 'FAILED'

export interface OrderItem {
  id: number
  product_id: number
  name: string
  unit_price: string
  quantity: number
  line_total: string
}

export interface Order {
  id: number
  user_id: number
  status: OrderStatus
  payment_status: 'PAID' | 'FAILED' | 'REFUNDED'
  payment_method: PaymentMethod
  full_name: string
  address_line1: string
  city: string
  state: string
  postal_code: string
  phone: string
  subtotal: string
  tax: string
  shipping: string
  total: string
  created_at: string
  updated_at: string
  items: OrderItem[]
}

export interface PurchaseStats {
  order_count: number
  total_spent: string
  items_purchased: number
  last_purchase_at: string | null
  average_days_between_orders: number | null
  top_products: { product_id: number; name: string; quantity: number; spent: string }[]
  cancelled_orders: number
  failed_orders: number
}
