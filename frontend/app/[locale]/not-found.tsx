import Link from 'next/link';
import { getDictionary } from './dictionaries';
import { locale } from 'next/root-params';
export default async function NotFound() { const dict = await getDictionary(); const current = await locale(); return <main id="main" className="error-page"><p className="eyebrow">SERTI · 404</p><h1>{dict.ui.notFound}</h1><Link className="text-link" href={`/${current}`}>{dict.ui.back} ↗</Link></main>; }
