import { cookies, draftMode } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { safePreviewPath } from '@/lib/routes';
export async function GET(req: NextRequest) {
  (await draftMode()).disable(); (await cookies()).delete('serti_preview');
  // Relative Location: req.url carries the internal bind address behind Caddy.
  const response = new NextResponse(null, { status: 307, headers: { Location: safePreviewPath(req.nextUrl.searchParams.get('path')) } });
  response.headers.set('Cache-Control', 'private, no-store'); return response;
}
