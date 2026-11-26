import { NextResponse, type NextRequest } from "next/server";
import { encodeOrderProbe, orderProbeHeader } from "@/lib/order-probe";

import { localeCookie, localeFromPath, negotiateLocale } from "@/lib/i18n";

import { trackingPath, trackingHttpStatus, unavailableTrackingHtml } from "@/lib/order-http";

import { routeDecision } from "@/lib/routes";
import { isDocumentRequest } from "@/lib/document-request";

// Internal re-render of a missing page; skips the existence probe to avoid a loop.
const notFoundRenderHeader = "x-serti-not-found-render";

import { protectDraftResponse } from '@/lib/cms-preview';

import { resolveCmsRedirect, redirectPathAllowed, type CmsRedirect } from '@/lib/cms-redirects';

const ONE_YEAR = 60 * 60 * 24 * 365;

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (redirectPathAllowed(pathname) && !request.cookies.has('__prerender_bypass')) {
    try {
      const api = (process.env.API_INTERNAL_URL ?? 'http://backend:8000/api/v1').replace(/\/$/, '');
      const headers: Record<string, string> = { Accept: 'application/json', 'X-Forwarded-Proto': 'https' };
      if (process.env.INTERNAL_API_TOKEN) headers['X-Internal-Token'] = process.env.INTERNAL_API_TOKEN;
      const response = await fetch(`${api}/cms/redirects`, { headers, next: { revalidate: 60 }, signal: AbortSignal.timeout(2000) });
      if (response.ok) {
        const rows: unknown = await response.json();
        const redirect = Array.isArray(rows) ? resolveCmsRedirect(pathname, rows as CmsRedirect[]) : null;
        if (redirect) {
          const url = request.nextUrl.clone(); url.pathname = redirect.pathname;
          return NextResponse.redirect(url, redirect.status);
        }
      }
    } catch { /* A temporary CMS outage must not block the storefront. */ }
  }
  // Never trust a browser-supplied preflight. These are request headers only,
  // overwritten on every proxy traversal, never returned to the browser.
  const forwarded = new Headers(request.headers);
  forwarded.delete(orderProbeHeader);
  const pathLocale = localeFromPath(pathname);

  if (pathLocale) {
    // Remember the language the visitor chose (CMS-04).
    const decision = routeDecision(pathname);
    const url = request.nextUrl.clone();
    url.pathname = decision.pathname;
    // Resolve missing dynamic resources before the React shell commits status 200.
    const parts = pathname.split('/').filter(Boolean);
    let missingResource = false;
    const staticSegments = new Set(['joyeria', 'jewelry', 'personaliza', 'customize', 'historia', 'story', 'contacto', 'contact', 'carrito', 'cart', 'checkout', 'deseos', 'wishlist', 'buscar', 'search', 'pedido', 'order', 'legal']);
    if (decision.kind !== 'redirect' && !request.cookies.has('__prerender_bypass') && isDocumentRequest(request.headers) && request.headers.get(notFoundRenderHeader) !== '1') {
      const segment = parts[1]; const slug = parts[2];
      const dynamic = slug && parts.length === 3 && ['piezas', 'pieces', 'joyeria', 'jewelry', 'piedras', 'stones', 'colecciones', 'collections'].includes(segment);
      const editorial = parts.length === 2 && segment && !staticSegments.has(segment);
      if (dynamic || editorial) {
        try {
          const api = (process.env.API_INTERNAL_URL ?? 'http://backend:8000/api/v1').replace(/\/$/, '');
          const headers: Record<string, string> = { Accept: 'application/json', 'X-Forwarded-Proto': 'https' };
          if (process.env.INTERNAL_API_TOKEN) headers['X-Internal-Token'] = process.env.INTERNAL_API_TOKEN;
          const kind = ['piezas', 'pieces'].includes(segment) ? 'piece' : ['joyeria', 'jewelry'].includes(segment) ? 'category' : ['piedras', 'stones'].includes(segment) ? 'stone' : 'collection';
          const path = editorial ? `cms/pages/${encodeURIComponent(segment)}` : `catalog/exists?${new URLSearchParams({ kind, slug: decodeURIComponent(slug), locale: pathLocale })}`;
          const probe = await fetch(`${api}/${path}${editorial ? `?locale=${pathLocale}` : ''}`, { headers, next: { revalidate: 60 }, signal: AbortSignal.timeout(8000) });
          if (probe.status === 404) missingResource = true;
          else if (probe.ok && editorial) {
            const data = await probe.json();
            missingResource = data.alternates?.[pathLocale] !== pathname;
          }
        } catch { /* API failures remain application errors, never false 404s. */ }
      }
    }
    if (missingResource) {
      // A prerendered (PPR) shell always commits 200, so a rewrite status is lost in production.
      // Render the same URL through this server (its not-found.tsx: same path, so hydration
      // matches) and return that HTML with a real 404. The public origin is TLS at Caddy and
      // not reachable from inside, hence 127.0.0.1.
      const target = new URL(`${pathname}${request.nextUrl.search}`, `http://127.0.0.1:${process.env.PORT ?? '3000'}`);
      const rendered = await fetch(target, { headers: { accept: 'text/html', 'accept-language': request.headers.get('accept-language') ?? '', [notFoundRenderHeader]: '1' }, cache: 'no-store' });
      const headers = new Headers(rendered.headers);
      for (const name of ['content-length', 'content-encoding', 'transfer-encoding', 'set-cookie']) headers.delete(name);
      // Internal routing directives of the inner render must not be re-applied to this response.
      for (const name of [...headers.keys()]) if (name.startsWith('x-middleware-')) headers.delete(name);
      headers.set('Cache-Control', 'no-store');
      headers.set('X-Robots-Tag', 'noindex, follow');
      return previewHeaders(request, new NextResponse(rendered.body, { status: 404, headers }));
    }
    let missingOrder = false;
    const tracking = trackingPath(pathname);
    if (tracking && decision.kind !== 'redirect') {
      const headers: Record<string, string> = { Accept: 'application/json', 'X-Forwarded-Proto': 'https' };
      if (process.env.INTERNAL_API_TOKEN) headers['X-Internal-Token'] = process.env.INTERNAL_API_TOKEN;
      const ip = request.headers.get('x-forwarded-for')?.split(',').at(-1)?.trim();
      if (ip) headers['X-Forwarded-For'] = ip;
      try {
        const api = (process.env.API_INTERNAL_URL ?? 'http://backend:8000/api/v1').replace(/\/$/, '');
        const probe = await fetch(`${api}/orders/${tracking.token}?locale=${tracking.locale}`, {
          headers, cache: 'no-store', signal: AbortSignal.timeout(8000),
        });
        missingOrder = trackingHttpStatus(probe.status) === 404;
        if (!missingOrder) {
          const body = await probe.json().catch(() => ({}));
          forwarded.set(orderProbeHeader, encodeOrderProbe({ token: tracking.token, locale: tracking.locale, status: probe.status, body }));
        }
      } catch { forwarded.set(orderProbeHeader, encodeOrderProbe({ token: tracking.token, locale: tracking.locale, status: 503, body: { code: 'network_unavailable' } })); }
    }
    // Finish missing/expired requests before React starts streaming. A rewrite
    // alone can still have its status replaced by the parent Suspense shell.
    const response = missingOrder ? new NextResponse(unavailableTrackingHtml(pathLocale), {
      status: 404, headers: { 'Content-Type': 'text/html; charset=utf-8' },
    }) : decision.kind === "redirect" ? NextResponse.redirect(url, 308)
      : decision.kind === "rewrite" ? NextResponse.rewrite(url, { request: { headers: forwarded } }) : NextResponse.next({ request: { headers: forwarded } });
    if (request.cookies.get(localeCookie)?.value !== pathLocale) {
      response.cookies.set(localeCookie, pathLocale, {
        maxAge: ONE_YEAR,
        sameSite: "lax",
        httpOnly: true,
        secure: request.nextUrl.protocol === "https:",
        path: "/",
      });
    }
    if (/^\/(es|en)\/(pedido|order)\//.test(pathname)) {
      response.headers.set('Cache-Control', 'no-store, private');
      response.headers.set('Referrer-Policy', 'no-referrer');
      response.headers.set('X-Robots-Tag', 'noindex, nofollow');
    }
    return previewHeaders(request, response);
  }

  const locale = negotiateLocale(
    request.cookies.get(localeCookie)?.value,
    request.headers.get("accept-language"),
  );
  const url = request.nextUrl.clone();
  url.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
  const response = NextResponse.redirect(url);
  if (/^\/(pedido|order)\//.test(pathname)) {
    response.headers.set('Cache-Control', 'no-store, private');
    response.headers.set('Referrer-Policy', 'no-referrer');
    response.headers.set('X-Robots-Tag', 'noindex, nofollow');
  }
  return previewHeaders(request, response);
}

export const config = {
  // Django owns /api, /static, /media and the admin path (routed by Caddy);
  // files with an extension and Next internals never need a locale.
  matcher: ["/es/pedido/:path*", "/en/pedido/:path*", "/es/order/:path*", "/en/order/:path*", "/((?!preview|api|dashboard|static|media|healthz|_next|.*\\..*).*)"],
};

export function previewHeaders(request: NextRequest, response: NextResponse) {
  protectDraftResponse(response.headers, request.cookies.has('__prerender_bypass'));
  return response;
}
