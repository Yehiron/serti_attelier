import { NextResponse, type NextRequest } from "next/server";

import { localeCookie, localeFromPath, negotiateLocale } from "@/lib/i18n";

const ONE_YEAR = 60 * 60 * 24 * 365;

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const pathLocale = localeFromPath(pathname);

  if (pathLocale) {
    // Remember the language the visitor chose (CMS-04).
    const response = NextResponse.next();
    if (request.cookies.get(localeCookie)?.value !== pathLocale) {
      response.cookies.set(localeCookie, pathLocale, {
        maxAge: ONE_YEAR,
        sameSite: "lax",
        secure: request.nextUrl.protocol === "https:",
        path: "/",
      });
    }
    return response;
  }

  const locale = negotiateLocale(
    request.cookies.get(localeCookie)?.value,
    request.headers.get("accept-language"),
  );
  const url = request.nextUrl.clone();
  url.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(url);
}

export const config = {
  // Django owns /api, /static, /media and the admin path (routed by Caddy);
  // files with an extension and Next internals never need a locale.
  matcher: ["/((?!api|static|media|healthz|_next|.*\\..*).*)"],
};
