/** Router requests do not need a document's HTTP status preflight. */
export function isDocumentRequest(headers: Headers): boolean {
  return !['rsc', 'next-router-prefetch', 'next-router-state-tree'].some(name => headers.has(name));
}
