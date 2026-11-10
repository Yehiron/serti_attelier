import { RegistrySection } from './registry-section';
import { EditorialTitle } from './editorial-title';
import Link from 'next/link';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Locale } from '@/lib/i18n';
import type { Cta, Section } from '@/lib/api/types';
import { Media, Ornament } from './media';
import { HeroCarousel } from './hero-carousel';
import { PieceCard } from './piece-card';
import { StonePanels, Rail } from './editorial-interactions';

function Action({ cta }: { cta: Cta | null }) {
  return cta && <Link className="text-link" href={cta.href} target={cta.external ? '_blank' : undefined} rel={cta.external ? 'noopener noreferrer' : undefined}>{cta.label} ↗</Link>;
}
function Paragraphs({ body }: { body: string }) {
  return body.split(/\n\s*\n/).map((text, i) => <p key={i}>{text}</p>);
}
type SectionOf<K extends Section['kind']> = Extract<Section, { kind: K }>;

function HeroSection({ section, dict, first }: { section: SectionOf<'hero'>; dict: Dictionary; first: boolean }) {
  const content = <>
    <div className="hero-copy">
      <p className="eyebrow">{dict.home.eyebrow}</p>
      {first ? <h1 className="title-reveal"><EditorialTitle text={section.title} /></h1> : <h2><EditorialTitle text={section.title} /></h2>}
      <p>{section.subtitle}</p><Action cta={section.cta} />
    </div>
    <div className="hero-caption"><span>{dict.home.status}</span><span>01 / SERTI</span></div>
  </>;
  return section.slides?.length ? <HeroCarousel slides={section.slides} labels={dict.home.carousel}>{content}</HeroCarousel> : <section className="hero">
    {section.image && <Media className="hero-image" image={section.image} priority={first} sizes="100vw" />}{content}
  </section>;
}
function StatementSection({ section, dict }: { section: SectionOf<'statement'>; dict: Dictionary }) {
  return <section className="statement wine">
    <p className="eyebrow">{dict.home.eyebrow}</p><h2><EditorialTitle text={section.title} /></h2><Ornament />
    <div className="body-copy"><Paragraphs body={section.body} /></div>
  </section>;
}
function CollectionSection({ section, locale, dict }: { section: SectionOf<'collection_rail'>; locale: Locale; dict: Dictionary }) {
  return <section className="rail-section">
    <div className="section-heading"><p className="eyebrow">{section.subtitle}</p><h2><EditorialTitle text={section.title} /></h2><Link className="text-link" href={section.collection.href}>{dict.ui.all} ↗</Link></div>
    <Rail previous={dict.ui.previous} next={dict.ui.next}>{section.pieces.map(piece => <PieceCard key={piece.sku} piece={piece} locale={locale} dict={dict} />)}</Rail>
    {!section.pieces.length && <p>{dict.ui.empty}</p>}
  </section>;
}
function CategoryGrid({ section, dict }: { section: SectionOf<'category_grid'>; dict: Dictionary }) {
  return <section className="category-section"><div className="section-heading"><p className="eyebrow">{section.subtitle}</p><h2><EditorialTitle text={section.title} /></h2></div><div className="category-grid">{section.categories.map(category => <Link key={category.slug} href={category.href} className={`category-card${category.image ? ' has-photo' : ''}`}>{category.image && <Media image={{ ...category.image, alt: '' }} sizes="(max-width: 760px) 50vw, 20vw" />}<div><h3>{category.name}</h3><small>{category.count} {dict.ui.results}</small></div><span aria-hidden="true">↗</span></Link>)}</div></section>;
}
function StorySection({ section }: { section: SectionOf<'story' | 'personalize' | 'banner'> }) {
  return <section className={`editorial-section ${section.kind === 'personalize' ? 'wine' : ''}`}>
    {section.image && <Media className="editorial-photo" image={section.image} />}
    <div><p className="eyebrow">SERTI · Colombia</p><h2><EditorialTitle text={section.title} /></h2><div className="body-copy"><Paragraphs body={section.body} /></div><Action cta={section.cta} /></div>
    {!section.image && <Ornament />}
  </section>;
}
export function HomeSection({ section, locale, dict, firstHero }: { section: Section; locale: Locale; dict: Dictionary; firstHero: boolean }) {
  switch (section.kind) {
    case 'hero': return <HeroSection section={section} dict={dict} first={firstHero} />;
    case 'category_grid': return <CategoryGrid section={section} dict={dict} />;
    case 'statement': return <StatementSection section={section} dict={dict} />;
    case 'stone_panels': return <StonePanels {...section} explore={dict.ui.explore} />;
    case 'collection_rail': return <CollectionSection section={section} locale={locale} dict={dict} />;
    case 'story': case 'personalize': case 'banner': return <StorySection section={section} />;
    case 'image_text': case 'faq': case 'process': return <RegistrySection section={section} />;
    default:
      console.warn('Se omite una sección CMS desconocida:', (section as { kind: string }).kind);
      return null;
  }
}
