'use client';
import { useEffect, useState, type ReactNode } from 'react';
import { getStatuses } from '@/lib/api/client';
import { liveState, type SaleState } from '@/lib/live-state';

// One request per SKU shared by the main CTA and the sticky mobile CTA.
const inflight = new Map<string, Promise<Record<string, string> | null>>();
function fetchStatus(sku: string): Promise<Record<string, string> | null> {
  const pending = inflight.get(sku) ?? getStatuses([sku]).then(r => r as Record<string, string>, () => null).finally(() => setTimeout(() => inflight.delete(sku), 1000));
  inflight.set(sku, pending);
  return pending;
}

/** Shows the CTA for the piece's live sale state; the server pre-renders every variant. */
export function LivePieceAction({ sku, initial, variants, notices, bare = false, secondary }: {
  sku: string;
  initial: SaleState;
  variants: Record<SaleState, ReactNode>;
  notices?: Partial<Record<SaleState, ReactNode>>;
  bare?: boolean;
  secondary?: Partial<Record<SaleState, ReactNode>>;
}) {
  const [state, setState] = useState<SaleState>(initial);
  useEffect(() => {
    let active = true;
    const refresh = () => { void fetchStatus(sku).then(statuses => { if (active) setState(current => liveState(current, statuses, sku)); }); };
    refresh();
    window.addEventListener('focus', refresh);
    return () => { active = false; window.removeEventListener('focus', refresh); };
  }, [sku]);
  if (bare) return <>{variants[state]}</>;
  return <>
    <div aria-live="polite">{notices?.[state]}</div>
    <div className="piece-action">{variants[state]}{secondary?.[state]}</div>
  </>;
}
