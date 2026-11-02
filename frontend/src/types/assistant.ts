export interface Explanation {
  fits_budget: boolean
  budget_note: string
  meets: string[]
  does_not_meet: string[]
  unknown: string[]
  info: string[]
  advantages: string[]
  limitations: string[]
  warranty: { months: number | null; type: string | null; service_coverage: string | null; statement: string }
  match_summary: string
}

export interface AdvisorCard {
  id: number
  name: string
  brand: string
  category: string
  price: string
  image: string
  stock: number
  stock_status: 'healthy' | 'low_stock' | 'out_of_stock'
  explanation?: Explanation
}

export interface Comparison {
  products: AdvisorCard[]
  rows: { label: string; values: Record<string, string> }[]
  leaders: { label: string; products: string[] }[]
}

export interface PendingAction {
  id: string
  type: 'add_to_cart'
  product_id: number
  quantity: number
  summary: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  payload: {
    cards?: AdvisorCard[]
    comparison?: Comparison
    pending_action?: PendingAction
    cart?: { item_count: number; total: string; link: string }
  }
  created_at: string
}

export interface Understood {
  summary: string
  priorities: string[]
  budget: { min: number | null; max: number | null }
  usage: string[]
}

export interface ConversationSummary {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[]
  pending_action: PendingAction | null
  understood: Understood
}
