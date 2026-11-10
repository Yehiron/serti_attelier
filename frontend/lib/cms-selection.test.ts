import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { sectionAttributes, selectionMessage } from './cms-selection.ts';

test('la tienda pública no contiene marcas editoriales; draft sí', () => {
  assert.equal(renderToStaticMarkup(createElement('section', sectionAttributes(false, 5))), '<section></section>');
  assert.match(renderToStaticMarkup(createElement('section', sectionAttributes(true, 5))), /data-cms-section="5"/);
});
test('selección exige draft, origen propio y una acción enumerada', () => {
  const value = {type:'cms:select',id:'5',scrollY:120};
  assert.deepEqual(selectionMessage(value,'https://serti.test','https://serti.test',true),{id:'5',scrollY:120});
  assert.equal(selectionMessage(value,'https://evil.test','https://serti.test',true),null);
  assert.equal(selectionMessage(value,'https://serti.test','https://serti.test',false),null);
  assert.equal(selectionMessage({...value,type:'eval'},'x','x',true),null);
  assert.equal(selectionMessage({...value,id:5},'x','x',true),null);
});

test('las cabeceras solo permiten enmarcar el borrador desde el mismo origen', async () => {
  const { protectDraftResponse } = await import('./cms-preview.ts');
  const headers = new Headers({'X-Frame-Options':'DENY'});
  protectDraftResponse(headers,true);
  assert.equal(headers.get('X-Frame-Options'),null);
  assert.equal(headers.get('Content-Security-Policy'),"frame-ancestors 'self'");
  const publicHeaders = new Headers();protectDraftResponse(publicHeaders,false);
  assert.equal(publicHeaders.get('X-Frame-Options'),'DENY');
  assert.equal(publicHeaders.get('Content-Security-Policy'),"frame-ancestors 'none'");
});
