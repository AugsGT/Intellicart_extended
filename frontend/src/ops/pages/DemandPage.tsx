import { useEffect, useState } from 'react'
import { getDemandOverview, getProductDemand, getProductDemandDetail, getRestockRecommendations, getSalesSeries } from '../api'
import type { DemandOverview, ProductDemand, ProductDemandDetail, SalesSeries, StockoutRisk, Trend } from '../types'
import { DemandChart, PeriodBars } from '../charts'
import StatCard from '../StatCard'
import { formatPrice } from '../../utils/format'

const TREND_LABEL: Record<Trend, string> = {
  increasing: 'Increasing',
  decreasing: 'Decreasing',
  stable: 'Stable',
  insufficient_data: 'Not enough history',
}

const RISK_LABEL: Record<StockoutRisk, string> = {
  ok: 'OK',
  warning: 'Running down',
  critical: 'Critical',
  stocked_out: 'Out of stock',
  no_recent_sales: 'No recent sales',
}

const SIGNAL_LABEL: Record<string, string> = {
  DEMAND_SPIKE: 'Demand spike',
  DEMAND_INCREASING: 'Demand rising',
  DEMAND_DECREASING: 'Demand falling',
  STOCK_SHORTAGE: 'Stock shortage',
  PREDICTED_STOCKOUT: 'Predicted stockout',
}

// Dates from the API are calendar days ("2026-11-10"). Parsing them directly would treat them as midnight UTC and
// show the previous day in timezones west of UTC, so build them as local dates instead.
const localDate = (iso: string) => new Date(`${iso}T00:00:00`)

const percent = (value: number | null) => (value === null ? '-' : `${value > 0 ? '+' : ''}${value.toFixed(0)}%`)

function shortDate(iso: string, month = false) {
  const date = localDate(iso)
  return month ? date.toLocaleDateString(undefined, { month: 'short', year: '2-digit' }) : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

/** Trailing 7-day moving average, so the "day" view can use the same chart as a product. */
function withMovingAverage(series: SalesSeries['series']) {
  return series.map((row, index) => {
    const window = series.slice(Math.max(0, index - 6), index + 1)
    return { date: row.period, units: row.units, moving_average_7d: window.reduce((sum, r) => sum + r.units, 0) / window.length }
  })
}

function TrendBadge({ item }: { item: ProductDemand }) {
  return (
    <>
      <span className={`badge badge-trend-${item.trend}`}>{TREND_LABEL[item.trend]}</span>
      {item.spike && <span className="badge badge-spike">Spike</span>}
    </>
  )
}

function DemandPage() {
  const [overview, setOverview] = useState<DemandOverview | null>(null)
  const [products, setProducts] = useState<ProductDemand[]>([])
  const [restock, setRestock] = useState<ProductDemand[]>([])
  const [sales, setSales] = useState<SalesSeries | null>(null)
  const [granularity, setGranularity] = useState<'day' | 'week' | 'month'>('week')
  const [selected, setSelected] = useState<ProductDemandDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getDemandOverview(), getProductDemand(), getRestockRecommendations()])
      .then(([overviewData, productData, restockData]) => {
        setOverview(overviewData)
        setProducts(productData)
        setRestock(restockData)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    getSalesSeries(granularity)
      .then(setSales)
      .catch((err: Error) => setError(err.message))
  }, [granularity])

  const openProduct = (productId: number) => {
    getProductDemandDetail(productId)
      .then(setSelected)
      .catch((err: Error) => setError(err.message))
  }

  if (loading) return <p>Loading demand intelligence...</p>
  if (error) return <p className="error-message">Could not load demand intelligence: {error}</p>
  if (!overview) return null

  const { counts } = overview

  return (
    <div>
      <div className="page-header">
        <h1>Demand Intelligence</h1>
        <span className="muted">Up to {localDate(overview.as_of).toLocaleDateString()} (last complete day)</span>
      </div>

      <details className="panel how-to-read">
        <summary>How to read this page (this is not a forecast)</summary>
        <ul>
          <li>
            Numbers come from <strong>completed orders only</strong>: cancelled and failed orders are never counted. Today is left out because it is not finished.
          </li>
          <li>
            <strong>Trend</strong> compares the last {overview.windows.recent_days} days with the {overview.windows.baseline_days} days before them. A product is
            &quot;increasing&quot; or &quot;decreasing&quot; only when the change is at least 25% <em>and</em> larger than normal week-to-week
            randomness (about two standard errors). Low-volume products therefore stay &quot;stable&quot; unless the change is clear.
          </li>
          <li>
            <strong>Spike</strong> means the last {overview.windows.spike_days} days are at least 6 units, at least double the usual pace, and above the usual pace plus
            three standard deviations.
          </li>
          <li>
            <strong>Days of cover</strong> is simply stock divided by the faster of the recent and earlier selling pace. It assumes that pace continues. A
            predicted stockout is when cover is under 7 days (the restock time).
          </li>
          <li>
            A <strong>stock shortage</strong> (stock already at its low-stock level), a <strong>predicted stockout</strong> (stock will run out soon at the current pace),
            a <strong>spike</strong> and a <strong>decline</strong> are four different things and are labelled separately.
          </li>
        </ul>
      </details>

      <div className="stats-grid">
        <StatCard label="Increasing" value={counts.increasing} />
        <StatCard label="Decreasing" value={counts.decreasing} />
        <StatCard label="Spikes" value={counts.spikes} accent={counts.spikes > 0 ? 'danger' : 'default'} />
        <StatCard label="Stock shortages" value={counts.stock_shortages} accent={counts.stock_shortages > 0 ? 'danger' : 'default'} />
        <StatCard label="Predicted stockouts" value={counts.predicted_stockouts} accent={counts.predicted_stockouts > 0 ? 'danger' : 'default'} />
      </div>

      <div className="overview-columns">
        <div className="panel">
          <h2>Sudden demand spikes</h2>
          {overview.spikes.length === 0 ? (
            <p className="muted">No spikes right now.</p>
          ) : (
            <ul className="simple-list">
              {overview.spikes.map((p) => (
                <li key={p.product_id}>
                  <span className="badge badge-spike">Spike</span>
                  <span>{p.name}</span>
                  <span className="muted small">
                    {p.burst_daily_average}/day vs usual {p.baseline_daily_average}/day
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="panel">
          <h2>Running out soon</h2>
          {overview.at_risk.length === 0 ? (
            <p className="muted">No predicted stockouts.</p>
          ) : (
            <ul className="simple-list">
              {overview.at_risk.map((p) => (
                <li key={p.product_id}>
                  <span className={`badge badge-risk-${p.stockout_risk}`}>{RISK_LABEL[p.stockout_risk]}</span>
                  <span>{p.name}</span>
                  <span className="muted small">
                    {p.stock} left{p.days_of_cover !== null ? `, about ${p.days_of_cover} days` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="panel">
        <h2>Restocking recommendations</h2>
        {restock.length === 0 ? (
          <p className="muted">Nothing needs reordering at the current pace.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Urgency</th>
                <th>In stock</th>
                <th>Days of cover</th>
                <th>Expected to run out</th>
                <th>Suggested order</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {restock.map((p) => (
                <tr key={p.product_id}>
                  <td>{p.name}</td>
                  <td>
                    <span className={`badge ${p.restock?.urgency === 'urgent' ? 'badge-risk-critical' : 'badge-risk-warning'}`}>{p.restock?.urgency}</span>
                  </td>
                  <td>{p.stock}</td>
                  <td>{p.days_of_cover ?? '-'}</td>
                  <td>{p.predicted_stockout_date ? localDate(p.predicted_stockout_date).toLocaleDateString() : '-'}</td>
                  <td>
                    <strong>{p.restock?.quantity}</strong> units
                  </td>
                  <td className="muted small">{p.restock?.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <div className="page-header">
          <h2>Total sales</h2>
          <div className="segmented">
            {(['day', 'week', 'month'] as const).map((option) => (
              <button key={option} type="button" className={granularity === option ? 'active' : ''} onClick={() => setGranularity(option)}>
                {option === 'day' ? 'Daily' : option === 'week' ? 'Weekly' : 'Monthly'}
              </button>
            ))}
          </div>
        </div>
        {sales && sales.series.length > 0 ? (
          <>
            {granularity === 'day' ? (
              <DemandChart daily={withMovingAverage(sales.series)} />
            ) : (
              <PeriodBars periods={sales.series} label={(period) => shortDate(period, granularity === 'month')} />
            )}
            <p className="muted small">
              {sales.series.reduce((sum, r) => sum + r.units, 0)} units, {formatPrice(sales.series.reduce((sum, r) => sum + r.revenue, 0))} over this view.
              {granularity === 'week' && ' Weeks start on Monday.'}
            </p>
          </>
        ) : (
          <p className="muted">No completed sales in this period.</p>
        )}
      </div>

      <div className="panel">
        <h2>Products</h2>
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>Demand</th>
              <th>Last 7 days</th>
              <th>Usual pace</th>
              <th>Change</th>
              <th>Stock</th>
              <th>Days of cover</th>
              <th>Stock risk</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.product_id} className="clickable-row" onClick={() => openProduct(p.product_id)}>
                <td>{p.name}</td>
                <td>
                  <TrendBadge item={p} />
                </td>
                <td>{p.recent_daily_average}/day</td>
                <td>{p.baseline_daily_average}/day</td>
                <td>{percent(p.change_pct)}</td>
                <td>{p.stock}</td>
                <td>{p.days_of_cover ?? '-'}</td>
                <td>
                  <span className={`badge badge-risk-${p.stockout_risk}`}>{RISK_LABEL[p.stockout_risk]}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">Click a product for its sales history.</p>
      </div>

      {selected && (
        <div className="panel">
          <div className="page-header">
            <h2>{selected.name}</h2>
            <button type="button" className="btn" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>

          <p className="muted small">Daily units sold (bars) and the 7-day moving average (line), last 90 days.</p>
          <DemandChart daily={selected.daily} />

          <div className="overview-columns">
            <div>
              <h3>Weekly units</h3>
              <PeriodBars periods={selected.weekly} label={(p) => shortDate(p)} />
            </div>
            <div>
              <h3>Monthly units</h3>
              <PeriodBars periods={selected.monthly} label={(p) => shortDate(p, true)} />
            </div>
          </div>

          <h3>Now compared with history</h3>
          <table>
            <tbody>
              <tr>
                <th>Last 7 days</th>
                <td>{selected.comparison.recent_week_units} units</td>
                <th>Previous 7 days</th>
                <td>
                  {selected.comparison.previous_week_units} units ({percent(selected.comparison.change_vs_previous_week_pct)})
                </td>
              </tr>
              <tr>
                <th>Usual week (28-day average)</th>
                <td>{selected.comparison.baseline_weekly_average} units</td>
                <th>Change vs usual</th>
                <td>{percent(selected.comparison.change_vs_baseline_pct)}</td>
              </tr>
            </tbody>
          </table>

          {selected.signals.length > 0 && (
            <>
              <h3>Signals</h3>
              <ul className="simple-list">
                {selected.signals.map((signal) => (
                  <li key={signal.type}>
                    <span className="badge">{SIGNAL_LABEL[signal.type]}</span>
                    <span>{signal.detail}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {selected.restock && <p>{selected.restock.reason}</p>}
        </div>
      )}
    </div>
  )
}

export default DemandPage
