import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// Every test starts with a clean page and empty browser storage.
afterEach(() => {
  cleanup()
  localStorage.clear()
})
