import { createElement as h, type CSSProperties } from 'react';
import { focalPosition } from '../lib/cms-focal.ts';
import type { Section } from '../lib/api/sections.generated.ts';

export type RegistrySectionData = Extract<Section, { kind: 'image_text' | 'faq' | 'process' }>;

/** Server component: details works without JS; only backend-sanitized Markdown is HTML. */
export function RegistrySection({ section }: { section: RegistrySectionData }) {
  if (section.kind === 'faq') return h('section', { className: 'faq-section cms-faq' },
    h('h2', null, section.title), section.items.map((item, index) => h('details', { key: index },
      h('summary', null, item.question), h('div', { className: 'prose', dangerouslySetInnerHTML: { __html: item.answer_html } }))));
  if (section.kind === 'process') return h('section', { className: 'process-section cms-process' },
    h('h2', null, section.title), h('ol', null, section.steps.map((step, index) => h('li', { key: index },
      h('span', { className: 'eyebrow', 'aria-hidden': true }, String(index + 1).padStart(2, '0')),
      h('h3', null, step.title), step.description ? h('p', null, step.description) : null))));
  const { image, mobile_image: mobile, cta } = section;
  return h('section', { className: `editorial-section cms-image-text image-${section.image_position}` },
    h('picture', { className: 'cms-section-photo' },
      mobile ? h('source', { media: '(max-width: 760px)', srcSet: mobile.srcset || mobile.src, width: mobile.width, height: mobile.height }) : null,
      h('img', { className: 'cms-focal-responsive', style: { '--cms-focal': focalPosition(image) || '50% 50%', '--cms-mobile-focal': focalPosition(mobile || image) || '50% 50%' } as CSSProperties, src: image.src, srcSet: image.srcset || undefined, width: image.width, height: image.height,
        sizes: '(max-width: 760px) 100vw, 50vw', alt: image.alt, loading: 'lazy' })),
    h('div', { className: 'cms-section-copy' }, section.eyebrow ? h('p', { className: 'eyebrow' }, section.eyebrow) : null,
      h('h2', null, section.title), h('div', { className: 'body-copy' }, section.body.split(/\n\s*\n/).map((paragraph, index) => h('p', { key: index }, paragraph))),
      cta ? h('a', { className: 'text-link', href: cta.href, target: cta.external ? '_blank' : undefined,
        rel: cta.external ? 'noopener noreferrer' : undefined }, `${cta.label} ↗`) : null));
}
