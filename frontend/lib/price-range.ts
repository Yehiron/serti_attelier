/** Price slider maths, in pesos (the URL unit); the API reports cents. */
export const PRICE_STEP = 50_000;

/** The catalogue's price span widened to whole steps, or null when there is nothing to slide. */
export function priceBounds(minCents: number | null, maxCents: number | null, step = PRICE_STEP): { min: number; max: number } | null {
  if (minCents == null || maxCents == null) return null;
  const min = Math.floor(minCents / 100 / step) * step;
  const max = Math.ceil(maxCents / 100 / step) * step;
  return max - min >= step ? { min, max } : null;
}

/** Snap a value to the step grid and keep it inside the bounds. */
export function snapPrice(value: number, bounds: { min: number; max: number }, step = PRICE_STEP): number {
  const snapped = bounds.min + Math.round((value - bounds.min) / step) * step;
  return Math.min(bounds.max, Math.max(bounds.min, snapped));
}

/** A query value in cents (as normalized by catalogQuery) back to pesos for the form. */
export function centsToPesos(value: string | null): number | null {
  if (value == null || value === '') return null;
  const cents = Number(value);
  return Number.isFinite(cents) ? Math.round(cents / 100) : null;
}
