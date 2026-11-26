'use client';
import { useState } from 'react';
import type { Taxonomy } from '@/lib/api/types';
import type { Locale } from '@/lib/i18n';
import { categoryKind, customizeMessage, customizeColor } from '@/lib/customize';
import { whatsappUrl } from '@/lib/api/format';
import { href } from '@/lib/routes';

type Copy = { builderTitle: string; builderIntro: string; type: string; stone: string; metal: string; note: string; optional: string; placeholder: string; advice: string; summary: string; jewel: string; with: string; send: string; response: string; contact: string; empty: string };
function Icon({ kind }: { kind: string }) {
  return <svg viewBox="0 0 48 48" aria-hidden="true">{kind === 'ring' ? <><circle cx="24" cy="29" r="12"/><path d="m19 14 5-6 5 6-5 4z"/></> : kind === 'earrings' ? <><path d="M16 8v8M32 8v8M16 30v6M32 30v6"/><circle cx="16" cy="24" r="6"/><circle cx="32" cy="24" r="6"/></> : kind === 'necklace' ? <><path d="M8 8c2 16 10 24 16 24S38 24 40 8"/><path d="m24 32-4 5 4 5 4-5z"/></> : kind === 'bracelet' ? <><ellipse cx="24" cy="24" rx="17" ry="11"/><ellipse cx="24" cy="24" rx="13" ry="7"/></> : <><circle cx="24" cy="24" r="14"/><path d="m24 14-7 10 7 10 7-10z"/></>}</svg>;
}
export function CustomizeBuilder({ taxonomy, locale, number, copy }: { taxonomy: Taxonomy; locale: Locale; number: string | null; copy: Copy }) {
  const [type, setType] = useState(taxonomy.categories[0]?.slug ?? '');
  const [stone, setStone] = useState(taxonomy.stones[0]?.slug ?? '');
  const [metal, setMetal] = useState(taxonomy.materials[0]?.slug ?? '');
  const [note, setNote] = useState('');
  const category = taxonomy.categories.find(x => x.slug === type);
  const selectedStone = taxonomy.stones.find(x => x.slug === stone);
  const selectedMetal = taxonomy.materials.find(x => x.slug === metal);
  const singular = category ? categoryKind(category.slug, category.name).singular : copy.empty;
  const base = selectedStone ? `${singular} ${copy.with} ${selectedStone.name.toLocaleLowerCase(locale)}` : singular;
  const title = base.charAt(0).toLocaleUpperCase(locale) + base.slice(1);
  const url = category ? whatsappUrl(number, customizeMessage(locale, singular, selectedStone?.name ?? null, selectedMetal?.name ?? null, note)) : null;
  return <section className="customize-builder" id="arma"><div className="customize-form"><h2>{copy.builderTitle}</h2><p>{copy.builderIntro}</p>
    <fieldset><legend><small>01</small>{copy.type}</legend><div className="customize-choices">{taxonomy.categories.map(x => <label className="customize-choice" key={x.slug}><input type="radio" name="customize-type" value={x.slug} checked={type === x.slug} onChange={() => setType(x.slug)}/><span><Icon kind={categoryKind(x.slug, x.name).icon}/>{x.name}</span></label>)}</div></fieldset>
    {([['02', copy.stone, taxonomy.stones, stone, setStone, false], ['03', copy.metal, taxonomy.materials, metal, setMetal, true]] as const).map(([num, label, items, value, setValue, isMetal]) => <fieldset key={num}><legend><small>{num}</small>{label}</legend><div className="customize-choices">{items.map(x => <label className="customize-choice" key={x.slug}><input type="radio" name={`customize-${num}`} value={x.slug} checked={value === x.slug} onChange={() => setValue(x.slug)}/><span><i className={isMetal ? 'customize-metal' : 'customize-gem'} style={{ background: customizeColor(x.name, isMetal, x.color) }}/> {x.name}</span></label>)}<label className="customize-choice"><input type="radio" name={`customize-${num}`} value="" checked={value === ''} onChange={() => setValue('')}/><span><Icon kind="generic"/>{copy.advice}</span></label></div></fieldset>)}
    <fieldset><legend><small>04</small><label htmlFor="customize-note">{copy.note}</label> <span className="customize-optional">({copy.optional})</span></legend><textarea id="customize-note" maxLength={300} value={note} onChange={e => setNote(e.target.value)} placeholder={copy.placeholder}/><div className="customize-count">{note.length}/300</div></fieldset>
  </div><aside className="customize-summary"><div className="customize-summary-image">{category?.cover && <img key={category.cover.src} src={category.cover.src} srcSet={category.cover.srcset} sizes="(max-width: 960px) 100vw, 40vw" width={category.cover.width} height={category.cover.height} alt={category.cover.alt}/>}</div><div className="customize-summary-body"><span className="eyebrow">{copy.summary}</span><h3 aria-live="polite">{title}</h3><dl><dt>{copy.jewel}</dt><dd>{category?.name ?? copy.empty}</dd><dt>{copy.stone}</dt><dd>{selectedStone?.name ?? copy.advice}</dd><dt>{copy.metal}</dt><dd>{selectedMetal?.name ?? copy.advice}</dd></dl>{url ? <a className="customize-cta" href={url} target="_blank" rel="noopener">{copy.send}</a> : <a className="customize-cta" href={href('contact', locale)}>{copy.contact}</a>}<small>{copy.response}</small></div></aside></section>;
}
