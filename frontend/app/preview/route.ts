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
  (await cookies()).set('serti_preview', token, { httpOnly: true, secure: true, sameSite: 'lax', maxAge: 600, path: '/' });
  const response = NextResponse.redirect(new URL(safePreviewPath(req.nextUrl.searchParams.get('path')), req.url));
  response.headers.set('Cache-Control', 'private, no-store'); response.headers.set('Referrer-Policy', 'no-referrer');
  return response;
}
