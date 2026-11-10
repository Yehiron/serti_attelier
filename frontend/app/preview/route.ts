import { draftMode, cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { request, ApiError } from '@/lib/api/server';
import { safePreviewPath } from '@/lib/routes';
export async function GET(req: NextRequest) {
  const token = req.nextUrl.searchParams.get('token');
  if (!token) return NextResponse.json({ code: 'preview_invalid' }, { status: 403 });
  try { await request<{ user: string; expires_at: string }>('cms/preview/verify', 'es', new URLSearchParams({ token }).toString()); }
  catch (error) { return NextResponse.json({ code: error instanceof ApiError ? error.problem.code : 'preview_invalid' }, { status: error instanceof ApiError ? error.status : 403 }); }
  (await draftMode()).enable();
  // The panel and the preview share an origin; Lax works inside its iframe, including local HTTP.
  const secure = req.nextUrl.protocol === 'https:' || req.headers.get('x-forwarded-proto') === 'https';
  const jar = await cookies();
  const bypass = jar.get('__prerender_bypass');
  if (bypass) jar.set('__prerender_bypass', bypass.value, { httpOnly: true, secure, sameSite: 'lax', path: '/' });
  (await cookies()).set('serti_preview', token, { httpOnly: true, secure, sameSite: 'lax', maxAge: 600, path: '/' });
  // Relative Location: behind Caddy, req.url carries the internal bind address (0.0.0.0:3000),
  // which the browser cannot reach. The browser resolves this path against the public origin.
  const response = new NextResponse(null, { status: 307, headers: { Location: safePreviewPath(req.nextUrl.searchParams.get('path')) } });
  response.headers.set('X-Robots-Tag', 'noindex, nofollow');
  response.headers.set('Cache-Control', 'private, no-store'); response.headers.set('Referrer-Policy', 'no-referrer');
  return response;
}
