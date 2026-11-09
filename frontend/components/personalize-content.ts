import { createElement as h, Fragment } from 'react';
import type { CmsPage } from '../lib/api/types.ts';

type Copy = { process: string; faq: string; steps: string[]; questions: string[]; answers: string[] };

/** API HTML has already passed through the CMS Markdown/nh3 pipeline. */
export function PersonalizeContent({ page, copy }: { page?: CmsPage | null; copy: Copy }) {
  const steps = page?.process?.steps ?? copy.steps.map(title => ({ title, description: '' }));
  return h(Fragment, null,
    h('section', { className: 'process-section' },
      h('h2', null, page?.process?.title ?? copy.process),
      h('ol', null, steps.map((step, index) => h('li', { key: index },
        h('span', { className: 'eyebrow' }, `0${index + 1}`), h('h3', null, step.title),
        step.description ? h('p', null, step.description) : null)))),
    h('section', { className: 'faq-section' }, h('h2', null, page?.faq?.title ?? copy.faq),
      page?.faq ? page.faq.items.map((item, index) => h('details', { key: index },
        h('summary', null, item.question), h('div', { dangerouslySetInnerHTML: { __html: item.answer_html } })))
        : copy.questions.map((question, index) => h('details', { key: index },
          h('summary', null, question), h('p', null, copy.answers[index])))));
}
