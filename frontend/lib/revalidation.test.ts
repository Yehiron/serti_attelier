import assert from 'node:assert/strict';
import test from 'node:test';
import { handleRevalidation } from './revalidation.ts';

const request = (tags: unknown, secret = 'shared-test', method = 'POST') => new Request('http://frontend/api/internal/revalidate', { method, headers: { 'x-revalidate-secret': secret }, ...(method === 'POST' ? { body: JSON.stringify({ tags }) } : {}) });
test('endpoint interno exige POST y secreto configurado y correcto', async () => {
  const invalidate = () => assert.fail('No debe invalidar');
  assert.equal((await handleRevalidation(request([], '', 'GET'), 'shared-test', invalidate)).status, 405);
  assert.equal((await handleRevalidation(request(['cms']), undefined, invalidate)).status, 503);
  for (const secret of ['', 'bad', 'shared-testx']) assert.equal((await handleRevalidation(request(['cms'], secret), 'shared-test', invalidate)).status, 401);
});
test('allowlist valida todo antes de invalidar; deduplica y acepta etiquetas estables', async () => {
  for (const tags of [[], ['orders'], ['cms:home', 'cms:evil'], ['cms:menu:other'], ['cms:page:../orders'], ['cms:*'], [null], 'cms', Array(51).fill('cms')]) {
    assert.equal((await handleRevalidation(request(tags), 'shared-test', () => assert.fail('No debe invalidar'))).status, 400);
  }
  const tags = ['cms','cms:home','cms:page:shipping','cms:menu:main','cms:menu:footer','cms:brand','cms:redirects','cms:settings','cms:personalization','catalog','piece:anillo'];
  const calls: string[] = [];
  const response = await handleRevalidation(request([...tags,'cms']), 'shared-test', tag => calls.push(tag));
  assert.equal(response.status, 200);
  assert.deepEqual(calls, tags);
});
test('JSON inválido y cuerpo excesivo se rechazan', async () => {
  for (const [body,status] of [['{',400], ['x'.repeat(8193),413]] as const) {
    assert.equal((await handleRevalidation(new Request('http://frontend', {method:'POST',headers:{'x-revalidate-secret':'s'},body}), 's', () => assert.fail())).status,status);
  }
});

test('lectores reales conservan preview privado y asignan tags con TTL largo', async () => {
  const {readFileSync} = await import('node:fs');
  const {createRequire} = await import('node:module');
  const ts = (await import('typescript')).default;
  const require = createRequire(import.meta.url);
  const tags: string[][] = [], lives: unknown[] = [], calls: string[] = [];
  let preview = false;
  const stubs: Record<string,unknown> = {
    'server-only': {},
    '../order-probe': {},
    'next/cache': {cacheTag: (...t:string[])=>tags.push(t), cacheLife:(life:unknown)=>lives.push(life)},
    'next/server': {connection:async()=>{}},
    'next/headers': {draftMode:async()=>({isEnabled:preview}),cookies:async()=>({get:()=>({value:'private-token'})})},
    react: {cache:(fn:unknown)=>fn},
    './problem': {ApiError:class extends Error {}, readResponse:async()=>({kind:'shipping'})},
  };
  const mod = {exports:{} as Record<string,(...args:unknown[])=>Promise<unknown>>};
  const js = ts.transpileModule(readFileSync(new URL('./api/server.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
  Function('require','module','exports','fetch',js)((name:string)=>stubs[name]??require(name),mod,mod.exports,async(url:string)=>{calls.push(url);return {};});
  for (const [method,args,tag] of [
    ['getHome',['es'],'cms:home'],['getBrand',['es'],'cms:brand'],['getMenu',['es','main'],'cms:menu:main'],
    ['getPage',['es','shipping',true],'cms:page:shipping'],['getPublishedPage',['es','envios'],'cms:pages'],
    ['getSettings',['es'],'cms:settings'],['getPersonalization',['es'],'cms:personalization'],
  ] as const) {
    await mod.exports[method](...args);
    assert.ok(tags.some(t=>t.includes(tag)&&t.includes('cms')));
  }
  assert.ok(lives.every(l=> (l as {revalidate:number}).revalidate===3600));
  preview=true;
  const count=tags.length;
  await mod.exports.getHome('es');
  await mod.exports.getPage('es','shipping',true);
  assert.equal(tags.length,count);
  assert.ok(calls.slice(-2).every(url=>url.includes('preview=private-token')));
});
