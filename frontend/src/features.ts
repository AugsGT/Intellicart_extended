// Switches for features whose Django endpoints arrived in a later migration phase
// (see docs/MIGRATION_PLAN.md). While a flag is off, the app does not call the endpoint.
export const FEATURES = {
  eventTracking: true, // Phase 5 done: checkout-started event (views and searches are recorded by the server)
  recommendations: true, // Phase 6 done
  interventions: true, // Phase 6 done
  shoppingAssistant: true, // Phase 7: conversational shopping advisor
}
