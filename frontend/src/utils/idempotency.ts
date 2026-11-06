/**
 * A fresh key for one checkout attempt. The server uses it so that a double click, or a retry
 * after a network timeout, cannot create a second order. Keys are 1-64 letters, digits, '-' or '_'.
 */
export function newIdempotencyKey(): string {
  return crypto.randomUUID()
}
