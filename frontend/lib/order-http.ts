// Validate before React can flush its Suspense shell (cacheComponents).
export function trackingPath(pathname: string): { locale: 'es' | 'en'; token: string } | null {
  const match = /^\/(es|en)\/(?:pedido|order)\/([^/]+)\/?$/.exec(pathname);
  if (!match) return null;
  return { locale: match[1] as 'es' | 'en', token: match[2] };
}
export function trackingHttpStatus(apiStatus: number): 404 | null {
  return apiStatus === 404 || apiStatus === 410 ? 404 : null;
}

// A complete response from the proxy cannot be turned into HTTP 200 by a
// parent Suspense boundary. No token or customer data is interpolated here.
export function unavailableTrackingHtml(language: 'es' | 'en'): string {
  const spanish = language === 'es';
  const title = spanish ? 'Este enlace de pedido ya no está disponible' : 'This order link is no longer available';
  const help = spanish ? 'Revisa el enlace que recibiste o comunícate con SERTI para consultar tu pedido.' : 'Check the link you received or contact SERTI about your order.';
  const home = spanish ? 'Volver a SERTI' : 'Return to SERTI';
  return `<!doctype html><html lang="${language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>${title} · SERTI</title><style>body{margin:0;background:#faf9f6;color:#292724;font:16px/1.6 Arial,sans-serif}main{max-width:780px;margin:12vh auto;padding:24px}h1{font:400 clamp(2rem,6vw,3.5rem)/1.15 Georgia,serif}a{display:inline-flex;align-items:center;min-height:44px;color:inherit;text-underline-offset:5px}a:focus-visible{outline:2px solid currentColor;outline-offset:4px}.brand{letter-spacing:.2em;font-size:.8rem}</style></head><body><main id="main"><p class="brand">SERTI · ${spanish ? 'PEDIDO' : 'ORDER'}</p><h1>${title}</h1><p>${help}</p><a href="/${language}">${home}</a></main></body></html>`;
}
