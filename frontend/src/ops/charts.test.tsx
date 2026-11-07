import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BarList, DemandChart, PeriodBars } from './charts'

const day = (n: number, units: number) => ({ date: `2026-11-${String(n).padStart(2, '0')}`, units, moving_average_7d: units / 2 })

describe('DemandChart', () => {
  it('draws one bar per day, labelled with its value, plus the moving-average line', () => {
    const { container } = render(<DemandChart daily={[day(1, 2), day(2, 8), day(3, 0)]} />)
    expect(container.querySelectorAll('rect.chart-bar')).toHaveLength(3)
    expect(container.querySelectorAll('path.chart-line')).toHaveLength(1)
    expect(screen.getByText('2026-11-02: 8 units')).toBeInTheDocument()
  })

  it('scales to the biggest value and does not break on all zeros', () => {
    const { container } = render(<DemandChart daily={[day(1, 0), day(2, 0)]} />)
    expect(container.querySelectorAll('rect.chart-bar')).toHaveLength(2)
  })
})

describe('PeriodBars', () => {
  it('shows each period with its units', () => {
    render(<PeriodBars periods={[{ period: '2026-11-02', units: 22 }, { period: '2026-11-09', units: 15 }]} label={(p) => `week ${p.slice(-2)}`} />)
    expect(screen.getByText('22')).toBeInTheDocument()
    expect(screen.getByText('week 09')).toBeInTheDocument()
  })

  it('says so when there is nothing to show', () => {
    render(<PeriodBars periods={[]} label={(p) => p} />)
    expect(screen.getByText('No sales in this period.')).toBeInTheDocument()
  })
})

describe('BarList', () => {
  it('sizes bars relative to the largest value and formats values', () => {
    const { container } = render(<BarList items={[{ label: 'Laptops', value: 200 }, { label: 'Phones', value: 100 }]} formatValue={(v) => `₹${v}`} />)
    const fills = [...container.querySelectorAll<HTMLElement>('.bar-fill')].map((el) => el.style.width)
    expect(fills).toEqual(['100%', '50%'])
    expect(screen.getByText('₹200')).toBeInTheDocument()
  })

  it('handles an empty list', () => {
    render(<BarList items={[]} />)
    expect(screen.getByText('No data yet.')).toBeInTheDocument()
  })
})
