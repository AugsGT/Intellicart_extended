import { Outlet, Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import InterventionBanner from './components/InterventionBanner'
import ShoppingAssistant from './components/ShoppingAssistant'
import RequireRole from './components/RequireRole'
import { FEATURES } from './features'
import ProductsPage from './pages/ProductsPage'
import ProductDetailsPage from './pages/ProductDetailsPage'
import CartPage from './pages/CartPage'
import PaymentPage from './pages/PaymentPage'
import OrderDetailPage from './pages/OrderDetailPage'
import ProfilePage from './pages/ProfilePage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import OpsLayout from './ops/OpsLayout'
import OpsOverviewPage from './ops/pages/OverviewPage'
import OpsOrdersPage from './ops/pages/OrdersPage'
import OpsInventoryPage from './ops/pages/InventoryPage'
import OpsAlertsPage from './ops/pages/AlertsPage'
import OpsEventsPage from './ops/pages/EventsPage'
import OpsSystemHealthPage from './ops/pages/SystemHealthPage'
import OpsInterventionsPage from './ops/pages/InterventionsPage'
import OpsCustomerIntelligencePage from './ops/pages/CustomerIntelligencePage'
import OpsDemandPage from './ops/pages/DemandPage'
import OpsAnalyticsPage from './ops/pages/AnalyticsPage'
import OpsAssistantPage from './ops/pages/AssistantPage'
import OpsAuditLogPage from './ops/pages/AuditLogPage'
import './App.css'

function StorefrontLayout() {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content">
        {FEATURES.interventions && <InterventionBanner />}
        <Outlet />
      </main>
      {FEATURES.shoppingAssistant && <ShoppingAssistant />}
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route element={<StorefrontLayout />}>
        <Route path="/" element={<ProductsPage />} />
        <Route path="/products/:id" element={<ProductDetailsPage />} />
        <Route path="/cart" element={<CartPage />} />
        <Route path="/payment" element={<PaymentPage />} />
        <Route path="/orders/:orderId" element={<OrderDetailPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      {/* Operations console: staff only (the API enforces the same rule). */}
      <Route
        path="/ops"
        element={
          <RequireRole roles={['ADMIN', 'OPERATIONS']}>
            <OpsLayout />
          </RequireRole>
        }
      >
        <Route index element={<OpsOverviewPage />} />
        <Route path="orders" element={<OpsOrdersPage />} />
        <Route path="inventory" element={<OpsInventoryPage />} />
        <Route path="alerts" element={<OpsAlertsPage />} />
        <Route path="events" element={<OpsEventsPage />} />
        <Route path="system" element={<OpsSystemHealthPage />} />
        <Route path="interventions" element={<OpsInterventionsPage />} />
        <Route path="customer-intelligence" element={<OpsCustomerIntelligencePage />} />
        <Route path="demand" element={<OpsDemandPage />} />
        <Route path="analytics" element={<OpsAnalyticsPage />} />
        <Route path="assistant" element={<OpsAssistantPage />} />
        <Route
          path="audit"
          element={
            <RequireRole roles={['ADMIN']}>
              <OpsAuditLogPage />
            </RequireRole>
          }
        />
      </Route>
    </Routes>
  )
}

export default App
