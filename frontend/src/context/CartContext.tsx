import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { Cart } from '../types/cart'
import { getCart, addCartItem, updateCartItem, removeCartItem } from '../api/cart'
import { useAuth } from './AuthContext'

interface CartContextValue {
  cart: Cart | null
  loading: boolean
  error: string | null
  itemCount: number
  addItem: (productId: number, quantity?: number) => Promise<void>
  removeItem: (itemId: number) => Promise<void>
  setQuantity: (itemId: number, quantity: number) => Promise<void>
  refresh: () => Promise<void>
}

const CartContext = createContext<CartContextValue | null>(null)

export function CartProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<Cart | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { user, loading: authLoading } = useAuth()

  const refresh = async () => {
    try {
      const data = await getCart()
      setCart(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cart')
    }
  }

  // Load the cart once we know who the shopper is, and again after login or logout
  // (a logged-in user has their own cart; a guest has this browser's cart).
  useEffect(() => {
    if (authLoading) return
    refresh().finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, authLoading])

  const addItem = async (productId: number, quantity = 1) => {
    const data = await addCartItem(productId, quantity)
    setCart(data)
  }

  const removeItem = async (itemId: number) => {
    const data = await removeCartItem(itemId)
    setCart(data)
  }

  const setQuantity = async (itemId: number, quantity: number) => {
    const data = await updateCartItem(itemId, quantity)
    setCart(data)
  }

  const itemCount = useMemo(
    () => cart?.items.reduce((sum, item) => sum + item.quantity, 0) ?? 0,
    [cart],
  )

  const value: CartContextValue = {
    cart,
    loading,
    error,
    itemCount,
    addItem,
    removeItem,
    setQuantity,
    refresh,
  }

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used within a CartProvider')
  return ctx
}
