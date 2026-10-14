import { apiFetch } from './client'
import type { User, RegisterRequest, LoginRequest, Tokens } from '../types/auth'
import { getRefreshToken } from '../utils/authToken'

export function register(payload: RegisterRequest) {
  return apiFetch<User>('/users/register/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function login(payload: LoginRequest) {
  return apiFetch<Tokens>('/auth/login/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function logout() {
  return apiFetch<{ detail: string }>('/auth/logout/', {
    method: 'POST',
    body: JSON.stringify({ refresh: getRefreshToken() ?? '' }),
  })
}

export function getMe() {
  return apiFetch<User>('/users/me/')
}
