import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useCart } from '../context/CartContext'
import { useAuth } from '../context/AuthContext'
import './Sidebar.css'

const NAV_ITEMS = [
  { to: '/', label: 'Products', icon: '\u{1F4E6}', end: true },
  { to: '/cart', label: 'Cart', icon: '\u{1F6D2}' },
  { to: '/payment', label: 'Payment', icon: '\u{1F4B3}' },
  { to: '/profile', label: 'Profile', icon: '\u{1F464}' },
]

// Shown only to ADMIN / OPERATIONS users. The server enforces access; this just hides the link.
const OPS_ITEM = { to: '/ops', label: 'Operations', icon: '\u{1F4CA}', end: false }

function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { itemCount } = useCart()
  const { isStaff } = useAuth()
  const navItems = isStaff ? [...NAV_ITEMS, OPS_ITEM] : NAV_ITEMS

  return (
    <>
      <button
        type="button"
        className="mobile-nav-toggle"
        onClick={() => setMobileOpen((open) => !open)}
        aria-label="Toggle navigation"
      >
        ☰
      </button>

      {mobileOpen && (
        <div className="sidebar-backdrop" onClick={() => setMobileOpen(false)} />
      )}

      <aside className={`sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>
        <div className="sidebar-header">
          <span className="sidebar-title">{collapsed ? 'IC' : 'IntelliCart'}</span>
          <button
            type="button"
            className="collapse-toggle"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? '»' : '«'}
          </button>
        </div>

        <nav>
          <ul className="nav-list">
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                  onClick={() => setMobileOpen(false)}
                >
                  <span className="nav-icon">{item.icon}</span>
                  <span className="nav-label">{item.label}</span>
                  {item.to === '/cart' && itemCount > 0 && (
                    <span className="nav-badge">{itemCount}</span>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
    </>
  )
}

export default Sidebar
