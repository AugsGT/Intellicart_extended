// Access and refresh tokens from the Django API. Stored in localStorage for now
// (simple, survives reloads); httpOnly cookies would be safer and can replace this later.
const ACCESS_KEY = 'intellicart_access'
const REFRESH_KEY = 'intellicart_refresh'

export function getToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens(access: string, refresh?: string): void {
  localStorage.setItem(ACCESS_KEY, access)
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearToken(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}
