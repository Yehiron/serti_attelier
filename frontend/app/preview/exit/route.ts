import { cookies, draftMode } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { safePreviewPath } from '@/lib/routes';
export async function GET(req: NextRequest) {
  (await draftMode()).disable(); (await cookies()).delete('serti_preview');
  const response = NextResponse.redirect(new URL(safePreviewPath(req.nextUrl.searchParams.get('path')), req.url));
  response.headers.set('Cache-Control', 'private, no-store'); return response;
}
