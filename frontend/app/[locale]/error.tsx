'use client';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import es from './dictionaries/es.json';
import en from './dictionaries/en.json';
export default function ErrorPage({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  const params = useParams(); const current = params.locale === 'en' ? 'en' : 'es'; const dict = current === 'en' ? en : es;
  return <main id="main" className="error-page"><p className="eyebrow">SERTI</p><h1>{dict.ui.error}</h1><button className="button" onClick={retry}>{dict.ui.retry}</button><Link className="text-link" href={`/${current}`}>{dict.ui.back} ↗</Link></main>;
}
