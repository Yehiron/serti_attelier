export type CmsRedirect = { from_path: string; to_path: string; status_code: 301 | 308 };
const excluded = new Set(['api', 'dashboard', '_next', 'media', 'static', 'preview']);
export function redirectPathAllowed(path: string): boolean {
  if (!/^\/(es|en)(\/[a-zA-Z0-9/_-]*)?$/.test(path) || path.includes('//')) return false;
  return !excluded.has(path.split('/')[2]);
}
export function resolveCmsRedirect(pathname: string, rows: readonly CmsRedirect[]): { pathname: string; status: 301 | 308 } | null {
  if (!redirectPathAllowed(pathname)) return null;
  const seen = new Set([pathname]);
  let path = pathname;
  let status: 301 | 308 | undefined;
  for (let i = 0; i <= rows.length; i++) {
    const row = rows.find(r => r?.from_path === path);
    if (!row) return status ? { pathname: path, status } : null;
    if (![301, 308].includes(row.status_code) || !redirectPathAllowed(row.to_path) || seen.has(row.to_path)) return null;
    status ??= row.status_code;
    path = row.to_path;
    seen.add(path);
  }
  return null;
}
