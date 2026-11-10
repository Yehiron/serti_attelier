/** Apply to localized responses as well as preview-entry redirects. */
export function protectDraftResponse(headers: Headers, isDraft: boolean) {
  if (!isDraft) {
    headers.set('X-Frame-Options', 'DENY');
    headers.set('Content-Security-Policy', "frame-ancestors 'none'");
  }
  if (isDraft) {
    headers.delete('X-Frame-Options');
    headers.set('Content-Security-Policy', "frame-ancestors 'self'");
    headers.set('Cache-Control', 'private, no-store');
    headers.set('X-Robots-Tag', 'noindex, nofollow');
    headers.set('Referrer-Policy', 'no-referrer');
  }
}

export function needsHomeFallback(home: { sections: unknown[]; published_at: string | null; preview: boolean }) {
  return home.sections.length === 0 && !home.published_at && !home.preview;
}
