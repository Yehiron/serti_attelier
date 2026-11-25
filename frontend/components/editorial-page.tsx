import { jsonLd } from '@/lib/seo';
import { brandMetadata, originalBrand } from '@/lib/cms-brand';
import { applyCmsSeo } from '@/lib/cms-seo';
import { siteUrl } from '@/lib/api/server';
import { draftMode } from 'next/headers';
import { CmsDraftSelection } from './cms-draft-selection';
import { sectionAttributes } from '@/lib/cms-selection';
import Link from 'next/link';
import { Contact } from './contact';
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
  const titles = current === 'es' ? { personalize: 'Joyas personalizadas en Armenia · Diseño a la medida | SERTI', contact: 'Contacto · Joyería con cita en Armenia, Quindío | SERTI', manufacturer: 'Nuestra historia · Joyería de autor en Armenia | SERTI' } : { personalize: 'Custom jewelry in Armenia · Made to measure | SERTI', contact: 'Contact · Jewelry by appointment in Armenia | SERTI', manufacturer: 'Our story · Fine jewelry from Armenia | SERTI' };
  const descriptions = current === 'es' ? { personalize: 'Diseñamos tu joya a la medida en Armenia, Quindío: anillos de compromiso, transformación de joyas y piezas con esmeralda colombiana en oro 18k. Agenda tu cita.', manufacturer: 'SERTI es una joyería de autor en Armenia, Quindío. Creamos piezas únicas a mano en oro 18k con esmeraldas colombianas, una sola vez y para una sola persona.', contact: 'Agenda tu cita con SERTI en Armenia, Quindío. Te atendemos por WhatsApp las 24 horas y enviamos tus joyas a toda Colombia.' } : { personalize: 'Design your custom jewelry in Armenia, Colombia: engagement rings, transformed jewelry and 18k gold pieces with Colombian emeralds. Book an appointment.', manufacturer: 'SERTI creates one-of-a-kind handmade 18k gold jewelry with Colombian emeralds in Armenia, Colombia, for one person and one story.', contact: 'Book an appointment with SERTI in Armenia, Colombia. Contact us on WhatsApp 24 hours a day and receive your jewelry throughout Colombia.' };
  return applyCmsSeo(brandMetadata({...brand, icon: null}, pageMetadata(kind === 'legal' ? title : titles[kind], kind === 'legal' ? dict.meta.description : descriptions[kind], current, alternates)), page?.seo, siteUrl, (await draftMode()).isEnabled);
}
export async function EditorialPage({ kind, slug }: { kind: EditorialKind; slug?: string }) {
  const { current, dict, page, title, alternates } = await context(kind, slug);
  const draft = (await draftMode()).isEnabled;
  const settings = await getSettings(current);
  const wine = kind === 'manufacturer' || kind === 'personalize';
  const general = kind === 'personalize' ? whatsappUrl(settings.whatsapp.number, `${dict.ui.customMessage} ___. ${dict.ui.customPrompt}`) : settings.whatsapp.general_url;
  return <main id="main" data-page-whatsapp={general ?? undefined} className={`editorial-page ${wine ? 'wine' : 'utility-page'} ${kind === 'contact' ? 'contact-page' : ''}`}><PageAlternates alternates={alternates} />{kind === 'personalize' && page?.faq?.items.length ? <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd({ '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: page.faq.items.map(item => ({ '@type': 'Question', name: item.question, acceptedAnswer: { '@type': 'Answer', text: item.answer_html } })) }) }} /> : null}{draft && <CmsDraftSelection />}<header {...sectionAttributes(draft, 'page')} className="page-heading"><p className="eyebrow">SERTI · Colombia</p><h1>{kind === 'contact' ? <>{dict.contact.titleStart} <em>{dict.contact.titleEnd}</em></> : title}</h1>{wine && <Ornament />}{kind === 'contact' && <p>{dict.contact.subtitle}</p>}</header>{page && page.body_html && (kind !== 'contact' || !['', 'Texto provisional — pendiente de revisión editorial', 'Provisional text — pending editorial review'].includes(page.body_html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim())) && (kind !== 'personalize' || page.body_visible) && <article {...sectionAttributes(draft, 'page')} className="prose" dangerouslySetInnerHTML={{ __html: page.body_html }} />}{!page && kind === 'manufacturer' && <p className="intro-copy">{dict.home.storyBody}</p>}
    {kind === 'legal' && page && <p className="legal-version">{dict.ui.version} {page.version} · {dict.ui.updated}: {new Intl.DateTimeFormat(current === 'es' ? 'es-CO' : 'en-US', { dateStyle: 'long', timeZone: 'America/Bogota' }).format(new Date(page.updated_at))}</p>}
    {kind === 'manufacturer' && <><Leather /><section className="editorial-section"><div><p className="eyebrow">{dict.home.eyebrow}</p><h2>{dict.ui.brand}</h2><p>{dict.home.statementBody}</p><Link className="text-link" href={href('catalog', current)}>{dict.ui.explore} ↗</Link></div><Ornament /></section></>}
    {kind === 'personalize' && <PersonalizeContent draft={draft} page={page} copy={dict.editorial} />}
    {kind === 'contact' && <Contact settings={settings} locale={current} copy={dict.contact} />}
  </main>;
}
