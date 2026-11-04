import { useEffect, useState } from 'react'
import { getBehaviourAnalytics, getRestockRecommendations, getSalesAnalytics } from '../api'
import type { BehaviourAnalytics, ProductDemand, SalesAnalytics } from '../types'
import { BarList } from '../charts'
import StatCard from '../StatCard'
import { formatPrice } from '../../utils/format'

const percent = (value: number) => `${(value * 100).toFixed(1)}%`

function AnalyticsPage() {
  const [behaviour, setBehaviour] = useState<BehaviourAnalytics | null>(null)
  const [sales, setSales] = useState<SalesAnalytics | null>(null)
  const [restock, setRestock] = useState<ProductDemand[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getBehaviourAnalytics(), getSalesAnalytics(), getRestockRecommendations()])
      .then(([behaviourData, salesData, restockData]) => {
        setBehaviour(behaviourData)
        setSales(salesData)
        setRestock(restockData)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p>Loading analytics...</p>
  if (error) return <p className="error-message">Could not load analytics: {error}</p>
  if (!behaviour || !sales) return null

  return (
    <div>
      <div className="page-header">
        <h1>Analytics</h1>
      </div>

      <div className="stats-grid">
        <StatCard label="Average Order Value" value={formatPrice(sales.average_order_value)} />
        <StatCard label="View-to-purchase" value={percent(sales.conversion.conversion_rate)} />
        <StatCard label="Checkout drop-off" value={percent(sales.checkout.drop_off_rate)} />
        <StatCard label="Restock suggested" value={restock.length} accent={restock.length > 0 ? 'danger' : 'default'} />
      </div>
      <p className="muted small">
        Revenue and order figures count completed orders only. View-to-purchase is the share of customers (accounts or browser
        sessions) who viewed a product and also bought. See Demand for sales trends and stock cover.
      </p>

      <div className="analytics-grid">
        <div className="panel">
          <h2>Most Viewed Products</h2>
          <BarList items={behaviour.most_viewed.map((p) => ({ label: p.name, value: p.views }))} />
        </div>
        <div className="panel">
          <h2>Most Added to Cart</h2>
          <BarList items={behaviour.most_added_to_cart.map((p) => ({ label: p.name, value: p.adds }))} />
        </div>
        <div className="panel">
          <h2>Most Searched Terms</h2>
          <BarList items={behaviour.most_searched.map((s) => ({ label: s.query, value: s.count }))} />
        </div>
        <div className="panel">
          <h2>Sales by Category</h2>
          <BarList
            items={sales.sales_by_category.map((c) => ({ label: c.category, value: parseFloat(c.revenue) }))}
            formatValue={(value) => formatPrice(value)}
          />
        </div>
      </div>
    </div>
  )
}

export default AnalyticsPage
