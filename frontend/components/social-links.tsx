import type { Settings } from '@/lib/api/types';
const labels = { instagram: 'Instagram', facebook: 'Facebook', tiktok: 'TikTok', pinterest: 'Pinterest' };
function SocialIcon({ network }: { network: Settings['social'][number]['network'] }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6">{
    network === 'instagram' ? <><rect x="3" y="3" width="18" height="18" rx="5" /><circle cx="12" cy="12" r="4" /><circle cx="17.5" cy="6.5" r=".8" fill="currentColor" stroke="none" /></> :
    network === 'facebook' ? <path fill="currentColor" stroke="none" d="M14 22v-9h3l.5-4H14V7c0-1 .4-1.5 1.7-1.5H18V2.2A24 24 0 0 0 15 2c-3 0-5 1.8-5 5v2H7v4h3v9z" /> :
    network === 'tiktok' ? <path d="M14 3v12a4 4 0 1 1-4-4M14 3c0 4 3 6 6 6V6c-2 0-3-1-3-3z" strokeWidth="2.6" /> :
    <><circle cx="12" cy="12" r="9" /><path d="m9 21 3-13m-1 7c6 4 9-8 3-9-5-1-8 5-5 8" /></>
  }</svg>;
}
export function SocialLinks({ social }: { social: Settings['social'] }) {
  return social.length > 0 && <div className="social-links">{social.map(({ network, url }) => <a key={network} href={url} aria-label={labels[network]} rel="noopener noreferrer" target="_blank"><SocialIcon network={network} /></a>)}</div>;
}
