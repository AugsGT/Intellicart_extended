import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import './AuthForm.css'

function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const me = await login(email, password)
      const from = (location.state as { from?: string } | null)?.from
      // Staff land in the operations console, customers where they came from.
      navigate(from ?? (me.role === 'CUSTOMER' ? '/profile' : '/ops'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not log in')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-form-page">
      <h1>Log In</h1>
      <form className="auth-form" onSubmit={handleSubmit}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="error-message">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? 'Logging in...' : 'Log In'}
        </button>
      </form>
      <p className="auth-form-switch">
        Don't have an account? <Link to="/register">Register</Link>
      </p>
    </div>
  )
}

export default LoginPage
