import { revalidateTag } from 'next/cache';
import { handleRevalidation } from '@/lib/revalidation';

// Node.js runtime is the default; `runtime` config is not allowed with cacheComponents.
export async function POST(request: Request) {
  // Next 16: expire immediately; "max" would serve a stale response on the next visit.
  return handleRevalidation(request, process.env.REVALIDATE_SECRET, tag => revalidateTag(tag, { expire: 0 }));
}
