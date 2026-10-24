export type SearchParams = Record<string, string | string[] | undefined>;
const allowed = ['category', 'collection', 'stone', 'material', 'price_min', 'price_max', 'availability', 'is_new', 'q', 'sort', 'page'];
export function catalogQuery(params: SearchParams, fixed: Record<string, string> = {}) {
  const query = new URLSearchParams();
  for (const key of allowed) {
    const value = params[key];
    if (Array.isArray(value)) { if (key === 'stone') query.set(key, value.flatMap(x => x.split(',')).filter(Boolean).join(',')); }
    else if (value && (key === 'price_min' || key === 'price_max')) {
      // Visitors filter in pesos (as shown on the site); the API expects cents.
      const pesos = /^\d{1,12}$/.test(value.trim()) ? Number(value.trim()) : NaN;
      if (Number.isSafeInteger(pesos)) query.set(key, String(pesos * 100));
    }
    else if (value) query.set(key, value);
  }
  for (const [key, value] of Object.entries(fixed)) query.set(key, value);
  if (!query.has('availability')) query.set('availability', 'available');
  return query;
}
