import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import './ops.css'

// Every page of the original operations dashboard is here, plus the Phase 9 assistant.
const NAV_ITEMS = [
  { to: '/ops', label: 'Overview', icon: '📊', end: true },
  { to: '/ops/orders', label: 'Orders', icon: '🧾' },
  { to: '/ops/inventory', label: 'Inventory', icon: '📦' },
  { to: '/ops/demand', label: 'Demand', icon: '📈' },
  { to: '/ops/events', label: 'Events', icon: '🔔' },
  { to: '/ops/alerts', label: 'Alerts', icon: '🚨' },
  { to: '/ops/interventions', label: 'Interventions', icon: '🎯' },
  { to: '/ops/customer-intelligence', label: 'Customer Intelligence', icon: '🧠' },
  { to: '/ops/analytics', label: 'Analytics', icon: '📊' },
  { to: '/ops/assistant', label: 'Assistant', icon: '🤖' },
  { to: '/ops/system', label: 'System Health', icon: '💻' },
]

// Administrators only. The server enforces this too; the link is just hidden from everyone else.
const ADMIN_ITEMS = [{ to: '/ops/audit', label: 'Audit Log', icon: '📜', end: false }]

function OpsLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="ops-shell">
      <aside className="ops-sidebar">
        <div className="ops-sidebar-header">
          <span className="ops-logo">IntelliCart</span>
          <span className="ops-logo-sub">Operations</span>
        </div>
        <nav>
          <ul className="ops-nav-list">
            {[...NAV_ITEMS, ...(user?.role === 'ADMIN' ? ADMIN_ITEMS : [])].map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `ops-nav-link ${isActive ? 'active' : ''}`}
                >
                  <span className="ops-nav-icon">{item.icon}</span>
                  {item.label}
                </NavLink>
              </li>
            ))}
            <li>
              <Link to="/" className="ops-nav-link">
                <span className="ops-nav-icon">🛍️</span>
                Storefront
              </Link>
            </li>
          </ul>
        </nav>
        <div className="ops-sidebar-footer">
          <div>
            <span className="ops-user-name">{user?.username}</span>
            <span className="ops-user-role">{user?.role}</span>
          </div>
          <button type="button" className="ops-logout-button" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </aside>
      <main className="ops-main">
        <Outlet />
      </main>
    </div>
  )
}

export default OpsLayout
