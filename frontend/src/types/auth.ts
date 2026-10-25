export type Role = 'CUSTOMER' | 'OPERATIONS' | 'ADMIN'

export const STAFF_ROLES: Role[] = ['ADMIN', 'OPERATIONS']

export interface User {
  id: number
  username: string
  email: string
  role: Role
  date_joined: string
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface Tokens {
  access: string
  refresh: string
}
