import type { StockStatus } from '../types/product'

export interface Overview {
  total_orders: number
  total_revenue: string
  open_alerts: number
  total_stock_units: number
}

export interface InventoryItem {
  product_id: number
  name: string
  stock: number
  low_stock_threshold: number
  status: StockStatus
}

export interface StockMovement {
  id: number
  change: number
  reason: string
  resulting_stock: number
  note: string
  reference: string
  created_at: string
}

export interface Alert {
  id: number
  type: string
  severity: string
  message: string
  product_id: number | null
  resolved: boolean
  created_at: string
  resolved_at: string | null
}

export interface EventRecord {
  id: number
  event_id: string
  event_type: string
  version: number
  user_id: number | null
  session_id: string
  entity_id: number | null
  payload: Record<string, unknown>
  occurred_at: string
  processed_at: string
}

export interface DeadLetter {
  id: number
  event_id: string
  event_type: string
  error: string
  retries: number
  created_at: string
  resolved_at: string | null
}

export interface QueueDepth {
  messages_ready: number
  messages_unacked: number
  consumers: number
}

export interface SystemHealth {
  outbox_pending: number
  outbox_oldest_pending_seconds: number | null
  outbox_failing: number
  events_last_hour: number
  last_event_processed_at: string | null
  dead_letters_unresolved: number
  queue: QueueDepth | null
  dead_letter_queue: QueueDepth | null
}

export interface Intervention {
  id: number
  user_id: number | null
  session_key: string
  trigger_event_type: string
  cart_value: string
  action: string
  rule: string
  signals: Record<string, unknown>
  message: string
  message_source: string
  status: string
  clicked_at: string | null
  outcome: string
  outcome_at: string | null
  created_at: string
}

export interface HighIntentCustomer {
  user_id: number | null
  session_id: string
  score: number
  tier: string
  computed_at: string
  basis: {
    view_count: number
    search_count: number
    cart_add_count: number
    cart_remove_count: number
    checkout_started: boolean
    prior_orders: number
  }
}

export interface RecommendationStat {
  kind: string
  served: number
  clicks: number
  purchases: number
  click_rate: number | null
  purchase_rate: number | null
}

// ---- demand intelligence ----
export type Trend = 'increasing' | 'decreasing' | 'stable' | 'insufficient_data'
export type StockoutRisk = 'ok' | 'warning' | 'critical' | 'stocked_out' | 'no_recent_sales'

export interface DemandSignal {
  type: 'DEMAND_SPIKE' | 'DEMAND_INCREASING' | 'DEMAND_DECREASING' | 'STOCK_SHORTAGE' | 'PREDICTED_STOCKOUT'
  detail: string
}

export interface RestockSuggestion {
  quantity: number
  urgency: 'urgent' | 'soon'
  reason: string
}

export interface ProductDemand {
  product_id: number
  name: string
  category: string
  recent_units: number
  baseline_units: number
  recent_daily_average: number
  baseline_daily_average: number
  burst_daily_average: number
  change_pct: number | null
  trend: Trend
  trend_z: number | null
  spike: boolean
  spike_threshold: number
  planning_velocity: number
  stock: number
  stock_state: 'healthy' | 'low_stock' | 'out_of_stock'
  days_of_cover: number | null
  stockout_risk: StockoutRisk
  predicted_stockout_date: string | null
  restock: RestockSuggestion | null
  signals: DemandSignal[]
  comparison: {
    recent_week_units: number
    previous_week_units: number
    change_vs_previous_week_pct: number | null
    baseline_weekly_average: number
    change_vs_baseline_pct: number | null
  }
}

export interface DemandOverview {
  as_of: string
  windows: { recent_days: number; baseline_days: number; spike_days: number }
  counts: {
    products: number
    with_sales: number
    increasing: number
    decreasing: number
    spikes: number
    stock_shortages: number
    predicted_stockouts: number
  }
  spikes: ProductDemand[]
  increasing: ProductDemand[]
  decreasing: ProductDemand[]
  at_risk: ProductDemand[]
  top_sellers: ProductDemand[]
}

export interface ProductDemandDetail extends ProductDemand {
  daily: { date: string; units: number; moving_average_7d: number }[]
  weekly: { period: string; units: number; revenue: number; orders: number }[]
  monthly: { period: string; units: number; revenue: number; orders: number }[]
}

export interface SalesSeries {
  granularity: 'day' | 'week' | 'month'
  days: number
  series: { period: string; units: number; revenue: number; orders: number }[]
}

// ---- analytics ----
export interface BehaviourAnalytics {
  most_viewed: { product_id: number; name: string; views: number }[]
  most_added_to_cart: { product_id: number; name: string; adds: number }[]
  most_searched: { query: string; count: number }[]
}

export interface SalesAnalytics {
  average_order_value: string
  sales_by_category: { category: string; revenue: string; units: number }[]
  checkout: { checkout_started: number; orders_completed: number; drop_off_rate: number }
  conversion: { customers_who_viewed: number; customers_who_bought: number; conversion_rate: number }
}

// ---- audit log ----
export interface AuditEntry {
  id: number
  created_at: string
  actor_label: string
  actor_role: string
  action: string
  entity_type: string
  entity_id: string
  summary: string
  details: Record<string, unknown>
  ip_address: string | null
}

export interface AuditAction {
  action: string
  description: string
}
