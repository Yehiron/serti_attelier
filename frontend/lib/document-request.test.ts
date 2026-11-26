import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { isDocumentRequest } from './document-request.ts';

test('only document requests need an existence probe', () => {
  assert.equal(isDocumentRequest(new Headers({ accept: 'text/html' })), true);
  for (const name of ['RSC', 'Next-Router-Prefetch', 'Next-Router-State-Tree']) {
    assert.equal(isDocumentRequest(new Headers({ [name]: '1' })), false, name);
  }
});
