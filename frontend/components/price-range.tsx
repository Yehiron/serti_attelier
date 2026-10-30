'use client';
import { useId, useState } from 'react';
import { formatCOP } from '@/lib/api/format';
import type { Locale } from '@/lib/i18n';
import { PRICE_STEP, snapPrice } from '@/lib/price-range';

/** Two-thumb price slider in pesos. Values at the ends are not submitted, so an untouched slider keeps the URL clean. */
export function PriceRange({ bounds, initialMin, initialMax, locale, label, minLabel, maxLabel }: { bounds: { min: number; max: number }; initialMin: number | null; initialMax: number | null; locale: Locale; label: string; minLabel: string; maxLabel: string }) {
  const id = useId();
  const [low, setLow] = useState(() => snapPrice(initialMin ?? bounds.min, bounds));
  const [high, setHigh] = useState(() => Math.max(snapPrice(initialMax ?? bounds.max, bounds), snapPrice(initialMin ?? bounds.min, bounds)));
  const span = bounds.max - bounds.min;
  const at = (value: number) => ((value - bounds.min) / span) * 100;
  const money = (value: number) => formatCOP(value * 100, locale);
  return <div className="filter-range" role="group" aria-labelledby={`${id}-label`}>
    <div className="filter-range-head"><span id={`${id}-label`} className="filter-row-name">{label}</span><output aria-live="polite">{money(low)} — {money(high)}</output></div>
    <div className="price-slider">
      <span className="price-track" aria-hidden="true"><span className="price-fill" style={{ left: `${at(low)}%`, right: `${100 - at(high)}%` }} /></span>
      {/* When both thumbs meet at the top end, the lower one must stay on top to be draggable. */}
      <input type="range" min={bounds.min} max={bounds.max} step={PRICE_STEP} value={low} aria-label={minLabel} aria-valuetext={money(low)} style={{ zIndex: low >= bounds.max - PRICE_STEP ? 3 : 2 }} onChange={event => setLow(Math.min(Number(event.target.value), high))} />
      <input type="range" min={bounds.min} max={bounds.max} step={PRICE_STEP} value={high} aria-label={maxLabel} aria-valuetext={money(high)} style={{ zIndex: 2 }} onChange={event => setHigh(Math.max(Number(event.target.value), low))} />
    </div>
    {low > bounds.min && <input type="hidden" name="price_min" value={low} />}
    {high < bounds.max && <input type="hidden" name="price_max" value={high} />}
  </div>;
}
