import { NextResponse, type NextRequest } from "next/server";
import { encodeOrderProbe, orderProbeHeader } from "@/lib/order-probe";

import { localeCookie, localeFromPath, negotiateLocale } from "@/lib/i18n";

import { trackingPath, trackingHttpStatus, unavailableTrackingHtml } from "@/lib/order-http";

import { routeDecision } from "@/lib/routes";

const ONE_YEAR = 60 * 60 * 24 * 365;

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
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
    return response;
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
  return response;
}

export const config = {
  // Django owns /api, /static, /media and the admin path (routed by Caddy);
  // files with an extension and Next internals never need a locale.
  matcher: ["/es/pedido/:path*", "/en/pedido/:path*", "/es/order/:path*", "/en/order/:path*", "/((?!preview|api|static|media|healthz|_next|.*\\..*).*)"],
};
