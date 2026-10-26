interface StatCardProps {
  label: string
  value: string | number
  accent?: 'default' | 'danger'
}

function StatCard({ label, value, accent = 'default' }: StatCardProps) {
  return (
    <div className={`stat-card ${accent === 'danger' ? 'stat-card-danger' : ''}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  )
}

export default StatCard
