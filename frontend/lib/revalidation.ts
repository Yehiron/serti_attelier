import { timingSafeEqual, createHash } from 'node:crypto';

const allowedTag = /^(?:cms(?::(?:home|brand|redirects|settings|personalization|pages|page:[a-z][a-z0-9_-]{0,63}|menu:(?:main|footer)))?|catalog|piece:[a-zA-Z0-9_-]{1,180})$/;

// Dependency injection keeps authentication and validation testable without a running Next server.
export async function handleRevalidation(request: Request, secret: string | undefined, invalidate: (tag: string) => void) {
  const reply = (status: number, error: string) => Response.json({ error }, { status, headers: { 'Cache-Control': 'no-store' } });
  if (request.method !== 'POST') return new Response(null, { status: 405, headers: { Allow: 'POST' } });
  if (!secret) {
    console.error('Invalidación CMS desactivada: falta REVALIDATE_SECRET.');
    return reply(503, 'Actualización temporalmente no disponible.');
  }
  const supplied = request.headers.get('x-revalidate-secret') ?? '';
  const digest = (value: string) => createHash('sha256').update(value).digest();
  if (!timingSafeEqual(digest(supplied), digest(secret))) return reply(401, 'No autorizado.');
  // Read a bounded stream, including when Content-Length is absent or incorrect.
  const reader = request.body?.getReader();
  if (!reader) return reply(400, 'Indica las etiquetas.');
  const chunks: Uint8Array[] = [];
  let length = 0;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    length += value.length;
    if (length > 8192) { await reader.cancel(); return reply(413, 'Solicitud demasiado grande.'); }
    chunks.push(value);
  }
  let body: unknown;
  try { body = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { return reply(400, 'JSON inválido.'); }
  if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).join() !== 'tags') return reply(400, 'Indica las etiquetas.');
  const tags = (body as { tags: unknown }).tags;
  if (!Array.isArray(tags) || tags.length < 1 || tags.length > 50 || tags.some(tag => typeof tag !== 'string' || !allowedTag.test(tag))) return reply(400, 'Etiquetas no permitidas.');
  for (const tag of new Set<string>(tags)) invalidate(tag);
  return Response.json({ ok: true }, { headers: { 'Cache-Control': 'no-store' } });
}
