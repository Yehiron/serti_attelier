import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('generated section contract matches the committed registry export', () => {
  const registry = JSON.parse(readFileSync(new URL('./api/section-registry.json', import.meta.url), 'utf8'));
  const lines = [
    '// Generado por manage.py export_section_registry --typescript. No editar.',
    "import type { Image, Cta, HeroSlide, Named, StonePanel, PieceCard } from './types';",
    'export type Section = { id: string | number; schema_version: 1 } & (',
  ];
  const sections = registry.sections as { kind: string; public_fields: [string, string][] }[];
  for (const section of sections) {
    const fields = section.public_fields.map(([key, value]) => `${key}: ${value}`).join('; ');
    lines.push(`  | { kind: '${section.kind}'; ${fields} }`);
  }
  lines.push(');', `export const sectionKinds = [${sections.map(s => `'${s.kind}'`).join(', ')}] as const;`, '');
  assert.equal(readFileSync(new URL('./api/sections.generated.ts', import.meta.url), 'utf8'), lines.join('\n'));
  assert.match(readFileSync(new URL('./api/types.ts', import.meta.url), 'utf8'), /export type \{ Section \} from '\.\/sections.generated'/);
});
