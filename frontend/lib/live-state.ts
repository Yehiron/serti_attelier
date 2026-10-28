export type SaleState = 'available' | 'reserved' | 'sold' | 'preorder';

const known: readonly SaleState[] = ['available', 'reserved', 'sold', 'preorder'];

/**
 * Piece pages are cached for a minute (ADR-013), so the server-rendered state can be stale.
 * The live status wins when it is a real sale state; "unavailable" or errors keep the page's.
 */
export function liveState(initial: SaleState, statuses: Record<string, string> | null, sku: string): SaleState {
  const value = statuses?.[sku];
  return known.includes(value as SaleState) ? (value as SaleState) : initial;
}
