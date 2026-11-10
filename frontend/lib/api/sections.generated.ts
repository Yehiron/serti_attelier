// Generado por manage.py export_section_registry --typescript. No editar.
import type { Image, Cta, HeroSlide, Named, StonePanel, PieceCard } from './types';
export type MediaReference = { asset: number; crop: '16:9' | '4:5' | '1:1'; version: number };
export type Section = { id: string | number; schema_version: 1 } & (
  | { kind: 'hero'; title: string; subtitle: string; image: Image | null; cta: Cta | null; slides?: HeroSlide[] }
  | { kind: 'statement'; title: string; body: string }
  | { kind: 'stone_panels'; title: string; subtitle: string; stones: StonePanel[] }
  | { kind: 'collection_rail'; title: string; subtitle: string; collection: Named & { href: string }; pieces: PieceCard[] }
  | { kind: 'story'; title: string; body: string; image: Image | null; cta: Cta | null }
  | { kind: 'personalize'; title: string; body: string; image: Image | null; cta: Cta | null }
  | { kind: 'banner'; title: string; body: string; image: Image | null; cta: Cta | null }
  | { kind: 'category_grid'; title: string; subtitle: string; categories: (Named & { href: string; count: number; image: Image | null })[] }
  | { kind: 'image_text'; title: string; eyebrow: string; body: string; image: Image; mobile_image: Image | null; cta: Cta | null; image_position: 'left' | 'right' }
  | { kind: 'faq'; title: string; items: { question: string; answer_html: string }[] }
  | { kind: 'process'; title: string; steps: { title: string; description: string }[] }
);
export const sectionKinds = ['hero', 'statement', 'stone_panels', 'collection_rail', 'story', 'personalize', 'banner', 'category_grid', 'image_text', 'faq', 'process'] as const;
