import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
function keys(value: unknown, prefix = ''): string[] { return value && typeof value === 'object' ? Object.entries(value).flatMap(([key,v]) => keys(v,`${prefix}.${key}`)) : [prefix]; }
test('Spanish and English dictionary leaf keys match', () => {
 const read = (locale: string) => JSON.parse(readFileSync(new URL(`../app/[locale]/dictionaries/${locale}.json`,import.meta.url),'utf8'));
 assert.deepEqual(keys(read('es')).sort(),keys(read('en')).sort());
});
