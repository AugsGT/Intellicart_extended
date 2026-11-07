import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import RequireRole from './RequireRole'
import type { Role, User } from '../types/auth'

const auth = vi.hoisted(() => ({ value: { user: null as User | null, loading: false } }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => auth.value }))

function user(role: Role): User {
  return { id: 1, username: 'u', email: 'u@example.com', role, date_joined: '' }
}

function renderAt(path: string, roles: Role[]) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<p>storefront</p>} />
        <Route path="/login" element={<p>login page</p>} />
        <Route
          path="/ops"
          element={
            <RequireRole roles={roles}>
              <p>operations console</p>
            </RequireRole>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RequireRole', () => {
  it('lets a permitted role in', () => {
    auth.value = { user: user('OPERATIONS'), loading: false }
    renderAt('/ops', ['ADMIN', 'OPERATIONS'])
    expect(screen.getByText('operations console')).toBeInTheDocument()
  })

  it('sends a logged-out visitor to the login page', () => {
    auth.value = { user: null, loading: false }
    renderAt('/ops', ['ADMIN', 'OPERATIONS'])
    expect(screen.getByText('login page')).toBeInTheDocument()
    expect(screen.queryByText('operations console')).not.toBeInTheDocument()
  })

  it('sends a customer back to the storefront', () => {
    auth.value = { user: user('CUSTOMER'), loading: false }
    renderAt('/ops', ['ADMIN', 'OPERATIONS'])
    expect(screen.getByText('storefront')).toBeInTheDocument()
    expect(screen.queryByText('operations console')).not.toBeInTheDocument()
  })

  it('keeps operations staff out of admin-only pages', () => {
    auth.value = { user: user('OPERATIONS'), loading: false }
    renderAt('/ops', ['ADMIN'])
    expect(screen.getByText('storefront')).toBeInTheDocument()
  })

  it('shows nothing sensitive while the session is still being checked', () => {
    auth.value = { user: null, loading: true }
    renderAt('/ops', ['ADMIN'])
    expect(screen.getByText('Loading...')).toBeInTheDocument()
    expect(screen.queryByText('operations console')).not.toBeInTheDocument()
  })
})
