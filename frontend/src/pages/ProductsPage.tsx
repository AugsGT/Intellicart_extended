import { useEffect, useState } from 'react'
import { getCategories, getProducts } from '../api/products'
import { getPersonalizedRecommendations, getRecentlyViewed } from '../api/recommendations'
import { useAuth } from '../context/AuthContext'
import type { Category, Product } from '../types/product'
import ProductCard from '../components/ProductCard'
import RecommendationSection from '../components/RecommendationSection'
import './ProductsPage.css'

const PAGE_SIZE = 12

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: 'name', label: 'Name (A-Z)' },
  { value: '-name', label: 'Name (Z-A)' },
  { value: 'price', label: 'Price (low to high)' },
  { value: '-price', label: 'Price (high to low)' },
  { value: 'newest', label: 'Newest first' },
]

function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [category, setCategory] = useState('')
  const [ordering, setOrdering] = useState('name')
  const [page, setPage] = useState(1)
  const [recentlyViewed, setRecentlyViewed] = useState<Product[]>([])
  const [personalized, setPersonalized] = useState<Product[]>([])
  const { user } = useAuth()

  useEffect(() => {
    getCategories()
      .then(setCategories)
      .catch(() => {})
    getRecentlyViewed()
      .then(setRecentlyViewed)
      .catch(() => {})
  }, [])

  // Personalized picks need a logged-in customer (they are built from that customer's history).
  useEffect(() => {
    if (!user) {
      setPersonalized([])
      return
    }
    getPersonalizedRecommendations()
      .then(setPersonalized)
      .catch(() => {})
  }, [user])

  // Wait for the shopper to stop typing, then search on the server.
  useEffect(() => {
    const timeout = setTimeout(() => {
      setDebouncedSearch(search.trim())
      setPage(1)
    }, 400)
    return () => clearTimeout(timeout)
  }, [search])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    getProducts({ q: debouncedSearch, category, ordering, page, page_size: PAGE_SIZE })
      .then((data) => {
        if (cancelled) return
        setProducts(data.results)
        setTotal(data.count)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [debouncedSearch, category, ordering, page])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="products-page">
      <h1>Products</h1>

      <RecommendationSection title="Recommended for you" icon="🎯" kind="personalized" products={personalized} />
      <RecommendationSection title="Recently Viewed" icon="🕒" kind="recently_viewed" products={recentlyViewed} />

      <div className="products-toolbar">
        <input
          type="search"
          placeholder="Search products..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="search-input"
        />

        <select
          value={category}
          onChange={(e) => {
            setCategory(e.target.value)
            setPage(1)
          }}
          aria-label="Category"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.parent ? `— ${c.name}` : c.name}
            </option>
          ))}
        </select>

        <select
          value={ordering}
          onChange={(e) => {
            setOrdering(e.target.value)
            setPage(1)
          }}
          aria-label="Sort"
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {loading && <p>Loading products...</p>}
      {error && (
        <p className="error-message">
          Couldn't load products: {error}. Is the backend running on {import.meta.env.VITE_API_URL ?? 'http://localhost:8001'}?
        </p>
      )}

      {!loading && !error && products.length === 0 && <p>No products match your search.</p>}

      {!loading && !error && products.length > 0 && (
        <>
          <div className="products-grid">
            {products.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>

          {pageCount > 1 && (
            <div className="pager">
              <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                ← Previous
              </button>
              <span>
                Page {page} of {pageCount} ({total} products)
              </span>
              <button type="button" disabled={page >= pageCount} onClick={() => setPage(page + 1)}>
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default ProductsPage
