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
  const help = spanish ? 'Este enlace ya no está disponible. Escríbenos y con gusto te ayudamos.' : 'This link is no longer available. Write to us and we will be happy to help.';
  const home = spanish ? 'Volver a SERTI' : 'Return to SERTI';
  const contact = spanish ? 'Contacto' : 'Contact';
  return `<!doctype html><html lang="${language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>${title} · SERTI</title><style>
  @font-face{font-family:Ninna;src:url('/fonts/ninna-regular.otf') format('opentype');font-display:swap}
  *{box-sizing:border-box}body{margin:0;background:#ead9cb;color:#330414;font:16px/1.6 Arial,sans-serif;min-height:100svh;display:flex;flex-direction:column}header,footer{padding:24px clamp(24px,5vw,88px);display:flex;align-items:center;justify-content:space-between;gap:24px}header{border-bottom:1px solid #651c3233}header img{display:block;width:160px;height:auto}main{width:100%;max-width:960px;margin:auto;padding:clamp(48px,12vh,120px) clamp(24px,5vw,88px)}h1{font:400 clamp(2.5rem,6vw,4.5rem)/1.1 Ninna,Georgia,serif;color:#651c32;max-width:780px}main p{max-width:540px}a{display:inline-flex;align-items:center;min-height:44px;color:inherit;text-underline-offset:5px}a:focus-visible{outline:2px solid currentColor;outline-offset:4px}.brand{letter-spacing:.18em;font-size:.75rem}.button{border:1px solid #651c32;padding:10px 24px;text-decoration:none;margin-top:16px;transition:opacity 180ms ease-out}.button:hover{opacity:.7}footer{background:#651c32;color:#ead9cb;font-size:.8rem}@media(prefers-reduced-motion:reduce){.button{transition:none}}</style></head><body><header class="site-header"><a href="/${language}" aria-label="SERTI · ${home}"><img src="/brand/logo/wordmark-wine.webp" width="320" height="103" alt="SERTI Jewelry Atelier"></a><a href="/${language}/${spanish ? 'contacto' : 'contact'}">${contact}</a></header><main id="main"><p class="brand">SERTI · ${spanish ? 'PEDIDO' : 'ORDER'}</p><h1>${title}</h1><p>${help}</p><a class="button" href="/${language}">${home} ↗</a></main><footer class="site-footer"><span>SERTI · Jewelry Atelier</span><a href="/${language}/${spanish ? 'contacto' : 'contact'}">${contact} ↗</a></footer></body></html>`;
}
