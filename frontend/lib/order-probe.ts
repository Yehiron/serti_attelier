// Server-only transport between the proxy and the render, never a shared cache.
import { deflateSync, inflateSync } from 'node:zlib';

export const orderProbeHeader = 'x-serti-order-probe';
export type OrderProbe = { token: string; locale: string; status: number; body: unknown };
export function encodeOrderProbe(probe: OrderProbe): string {
  return deflateSync(Buffer.from(JSON.stringify(probe))).toString('base64');
}
export function decodeOrderProbe(value: string | null, token: string, locale: string): OrderProbe | null {
  if (!value) return null;
  try {
    const probe = JSON.parse(inflateSync(Buffer.from(value, 'base64'), { maxOutputLength: 1024 * 1024 }).toString('utf8')) as OrderProbe;
    return probe.token === token && probe.locale === locale && Number.isInteger(probe.status) ? probe : null;
  } catch { return null; }
}
