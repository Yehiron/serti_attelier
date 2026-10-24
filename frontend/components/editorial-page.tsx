import Link from 'next/link';
import { locale } from 'next/root-params';
import { notFound } from 'next/navigation';
import { getDictionary } from '@/app/[locale]/dictionaries';
import { ApiError, getPage, getSettings, getPersonalization, optionalPage, getCatalog } from '@/lib/api/server';
import { isLocale } from '@/lib/i18n';
import { href } from '@/lib/routes';
import { whatsappUrl } from '@/lib/api/format';
import { pageMetadata, PageAlternates } from '@/lib/metadata';
import { Ornament, Leather, Media } from './media';
import { PieceCard } from './piece-card';
export type EditorialKind = 'personalize' | 'manufacturer' | 'contact' | 'legal';
async function context(kind: EditorialKind, slug?: string) {
  const current = await locale(); if (!isLocale(current)) notFound();
  const dict = await getDictionary();
  let page;
  try { page = kind === 'legal' ? await getPage(current, slug!) : await optionalPage(current, kind); }
  catch (error) { if (error instanceof ApiError && error.status === 404) notFound(); throw error; }
  const key = kind === 'manufacturer' ? 'story' : kind === 'legal' ? 'legal' : kind;
  const title = page?.title ?? (kind === 'manufacturer' ? dict.editorial.storyTitle : kind === 'personalize' ? dict.editorial.personalizeTitle : dict.editorial.contactTitle);
  const alternates = page?.alternates ?? { es: href(key, 'es', slug), en: href(key, 'en', slug) };
  return { current, dict, page, title, alternates };
}
export async function editorialMetadata(kind: EditorialKind, slug?: string) {
  const { current, dict, title, alternates } = await context(kind, slug);
  return pageMetadata(title, dict.meta.description, current, alternates);
}
export async function EditorialPage({ kind, slug }: { kind: EditorialKind; slug?: string }) {
  const { current, dict, page, title, alternates } = await context(kind, slug);
  const settings = await getSettings(current);
  const wine = kind === 'manufacturer' || kind === 'personalize';
  const general = kind === 'personalize' ? whatsappUrl(settings.whatsapp.number, `${dict.ui.customMessage} ___. ${dict.ui.customPrompt}`) : settings.whatsapp.general_url;
  const services = kind === 'personalize' ? (await getPersonalization(current)).services : [];
  const inspiration = kind === 'personalize' ? (await getCatalog(current, 'availability=all&page_size=48')).results.filter(x => x.sale_state === 'sold').slice(0, 4) : [];
  return <main id="main" data-page-whatsapp={general ?? undefined} className={`editorial-page ${wine ? 'wine' : 'utility-page'}`}><PageAlternates alternates={alternates} /><header className="page-heading"><p className="eyebrow">SERTI · Colombia</p><h1>{title}</h1>{wine && <Ornament />}{kind === 'contact' && <p>{dict.ui.contactIntro}</p>}</header>{page && <article className="prose" dangerouslySetInnerHTML={{ __html: page.body_html }} />}{!page && wine && <p className="intro-copy">{kind === 'manufacturer' ? dict.home.storyBody : dict.home.customBody}</p>}
    {kind === 'legal' && page && <p className="legal-version">{dict.ui.version} {page.version} · {dict.ui.updated}: {new Intl.DateTimeFormat(current === 'es' ? 'es-CO' : 'en-US', { dateStyle: 'long', timeZone: 'America/Bogota' }).format(new Date(page.updated_at))}</p>}
    {kind === 'manufacturer' && <><Leather /><section className="editorial-section"><div><p className="eyebrow">{dict.home.eyebrow}</p><h2>{dict.ui.brand}</h2><p>{dict.home.statementBody}</p><Link className="text-link" href={href('catalog', current)}>{dict.ui.explore} ↗</Link></div><Ornament /></section></>}
    {kind === 'personalize' && <><section className="service-section"><h2>{dict.nav.personalize}</h2>{services.length ? <div className="services">{services.map(service => <article key={service.id}>{service.image && <Media image={service.image} sizes="(max-width:700px) 100vw, 33vw" />}<h3>{service.title}</h3><p>{service.description}</p>{service.whatsapp_url && <a className="text-link" href={service.whatsapp_url} target="_blank" rel="noopener noreferrer">{dict.ui.whatsapp} ↗</a>}</article>)}</div> : <p>{dict.ui.noServices}</p>}{!services.length && general && <a className="text-link" href={general} target="_blank" rel="noopener noreferrer">{dict.ui.whatsapp} ↗</a>}</section><section className="process-section"><h2>{dict.editorial.process}</h2><ol>{dict.editorial.steps.map((step, index) => <li key={step}><span className="eyebrow">0{index + 1}</span><h3>{step}</h3></li>)}</ol></section><section className="prepare-section"><h2>{dict.editorial.prepare}</h2><p>{dict.editorial.prepareBody}</p></section>{inspiration.length > 0 && <section className="inspiration"><h2>{dict.editorial.inspiration}</h2><div className="piece-grid">{inspiration.map(piece => <PieceCard key={piece.sku} piece={piece} locale={current} dict={dict} />)}</div></section>}<section className="faq-section"><h2>{dict.editorial.faq}</h2>{dict.editorial.questions.map((question, i) => <details key={question}><summary>{question}</summary><p>{dict.editorial.answers[i]}</p>{i === 2 && settings.legal_pages.filter(x => x.kind === 'returns').map(x => <Link key={x.kind} className="text-link" href={x.href}>{x.title}</Link>)}</details>)}</section>{general && <div className="final-cta"><h2>{dict.home.customTitle}</h2><a className="button" href={general} target="_blank" rel="noopener noreferrer">{dict.ui.whatsapp} ↗</a></div>}</>}
    {kind === 'contact' && <section className="contact-links">{general && <a className="button" href={general} target="_blank" rel="noopener noreferrer">{dict.ui.whatsapp} ↗</a>}{settings.support_email && <div><h2>{dict.ui.email}</h2><a href={`mailto:${settings.support_email}`}>{settings.support_email}</a></div>}{settings.social.length > 0 && <div><h2>{dict.ui.social}</h2>{settings.social.map(social => <a className="text-link" key={social.network} href={social.url} target="_blank" rel="noopener noreferrer">{social.network} ↗</a>)}</div>}</section>}
  </main>;
}
