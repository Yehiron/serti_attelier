import { readResponse } from './problem';
import type { LiveState } from './types';
export async function getStatuses(skus: string[], signal?: AbortSignal): Promise<Record<string, LiveState>> {
  const batches = Array.from({ length: Math.ceil(skus.length / 50) }, (_, i) => skus.slice(i * 50, (i + 1) * 50));
  const results = await Promise.all(batches.map(async batch => readResponse<Record<string, LiveState>>(await fetch(`/api/v1/catalog/pieces/status?${new URLSearchParams({ skus: batch.join(',') })}`, { signal, cache: 'no-store', headers: { Accept: 'application/json' } }))));
  return Object.assign({}, ...results);
}
