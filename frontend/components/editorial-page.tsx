import { brandMetadata, originalBrand } from '@/lib/cms-brand';
import { applyCmsSeo } from '@/lib/cms-seo';
import { siteUrl } from '@/lib/api/server';
import { draftMode } from 'next/headers';
import { CmsDraftSelection } from './cms-draft-selection';
import { sectionAttributes } from '@/lib/cms-selection';
import Link from 'next/link';
import { PersonalizeContent } from './personalize-content';
import { locale } from 'next/root-params';
import { notFound } from 'next/navigation';
import { getDictionary } from '@/app/[locale]/dictionaries';
import { ApiError, getBrand, getPage, getSettings, optionalPage } from '@/lib/api/server';
import { isLocale } from '@/lib/i18n';
import { href } from '@/lib/routes';
import { whatsappUrl } from '@/lib/api/format';
import { pageMetadata, PageAlternates } from '@/lib/metadata';
import { Ornament, Leather } from './media';
export type EditorialKind = 'personalize' | 'manufacturer' | 'contact' | 'legal';
async function context(kind: EditorialKind, slug?: string) {
  const current = await locale(); if (!isLocale(current)) notFound();
  const dict = await getDictionary();
  let page;
  try { page = slug ? await getPage(current, slug) : await optionalPage(current, kind); }
  catch (error) { if (error instanceof ApiError && error.status === 404) notFound(); throw error; }
  const key = kind === 'manufacturer' ? 'story' : kind === 'legal' ? 'legal' : kind;
  const title = page?.title ?? (kind === 'manufacturer' ? dict.editorial.storyTitle : kind === 'personalize' ? dict.editorial.personalizeTitle : dict.editorial.contactTitle);
  const alternates = page?.alternates ?? { es: href(key, 'es', slug), en: href(key, 'en', slug) };
  return { current, dict, page, title, alternates };
}
export async function editorialMetadata(kind: EditorialKind, slug?: string) {
  const { current, dict, page, title, alternates } = await context(kind, slug);
  const brand = await getBrand(current).catch(() => originalBrand);
  return applyCmsSeo(brandMetadata({...brand, icon: null}, pageMetadata(title, dict.meta.description, current, alternates)), page?.seo, siteUrl, (await draftMode()).isEnabled);
}
export async function EditorialPage({ kind, slug }: { kind: EditorialKind; slug?: string }) {
  const { current, dict, page, title, alternates } = await context(kind, slug);
  const draft = (await draftMode()).isEnabled;
  const settings = await getSettings(current);
  const wine = kind === 'manufacturer' || kind === 'personalize';
  const general = kind === 'personalize' ? whatsappUrl(settings.whatsapp.number, `${dict.ui.customMessage} ___. ${dict.ui.customPrompt}`) : settings.whatsapp.general_url;
  return <main id="main" data-page-whatsapp={general ?? undefined} className={`editorial-page ${wine ? 'wine' : 'utility-page'}`}><PageAlternates alternates={alternates} />{draft && <CmsDraftSelection />}<header {...sectionAttributes(draft, 'page')} className="page-heading"><p className="eyebrow">SERTI · Colombia</p><h1>{title}</h1>{wine && <Ornament />}{kind === 'contact' && <p>{dict.ui.contactIntro}</p>}</header>{page && page.body_html && (kind !== 'personalize' || page.body_visible) && <article {...sectionAttributes(draft, 'page')} className="prose" dangerouslySetInnerHTML={{ __html: page.body_html }} />}{!page && kind === 'manufacturer' && <p className="intro-copy">{dict.home.storyBody}</p>}
    {kind === 'legal' && page && <p className="legal-version">{dict.ui.version} {page.version} · {dict.ui.updated}: {new Intl.DateTimeFormat(current === 'es' ? 'es-CO' : 'en-US', { dateStyle: 'long', timeZone: 'America/Bogota' }).format(new Date(page.updated_at))}</p>}
    {kind === 'manufacturer' && <><Leather /><section className="editorial-section"><div><p className="eyebrow">{dict.home.eyebrow}</p><h2>{dict.ui.brand}</h2><p>{dict.home.statementBody}</p><Link className="text-link" href={href('catalog', current)}>{dict.ui.explore} ↗</Link></div><Ornament /></section></>}
    {kind === 'personalize' && <PersonalizeContent draft={draft} page={page} copy={dict.editorial} />}
    {kind === 'contact' && <section className="contact-links">{general && <a className="button" href={general} target="_blank" rel="noopener noreferrer">{dict.ui.whatsapp} ↗</a>}{settings.support_email && <div><h2>{dict.ui.email}</h2><a href={`mailto:${settings.support_email}`}>{settings.support_email}</a></div>}{settings.social.length > 0 && <div><h2>{dict.ui.social}</h2>{settings.social.map(social => <a className="text-link" key={social.network} href={social.url} target="_blank" rel="noopener noreferrer">{social.network} ↗</a>)}</div>}</section>}
  </main>;
}
