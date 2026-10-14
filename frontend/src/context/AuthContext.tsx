import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { User } from '../types/auth'
import { STAFF_ROLES } from '../types/auth'
import * as authApi from '../api/auth'
import { mergeCart } from '../api/cart'
import { SESSION_EXPIRED_EVENT } from '../api/client'
import { getToken, setTokens, clearToken } from '../utils/authToken'

interface AuthContextValue {
  user: User | null
  loading: boolean
  isStaff: boolean
  login: (email: string, password: string) => Promise<User>
  register: (username: string, email: string, password: string) => Promise<User>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!getToken()) {
      setLoading(false)
      return
    }
    authApi
      .getMe()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setLoading(false))
  }, [])

  // The API client fires this when the refresh token no longer works.
  useEffect(() => {
    const onExpired = () => setUser(null)
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired)
  }, [])

  const login = async (email: string, password: string) => {
    const tokens = await authApi.login({ email, password })
    setTokens(tokens.access, tokens.refresh)
    // Bring the cart built while browsing as a guest into the account.
    await mergeCart().catch(() => {})
    const me = await authApi.getMe()
    setUser(me)
    return me
  }

  const register = async (username: string, email: string, password: string) => {
    await authApi.register({ username, email, password })
    return login(email, password)
  }

  const logout = async () => {
    try {
      await authApi.logout()
    } catch {
      // token may already be invalid/expired - clear local state regardless
    }
    clearToken()
    setUser(null)
  }

  const isStaff = user !== null && STAFF_ROLES.includes(user.role)

  return (
    <AuthContext.Provider value={{ user, loading, isStaff, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
