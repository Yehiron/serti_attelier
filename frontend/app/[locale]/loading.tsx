import { getDictionary } from './dictionaries';
export default async function Loading() { const dict = await getDictionary(); return <main id="main" className="loading-shell" aria-busy="true"><p className="eyebrow">SERTI</p><p>{dict.ui.loading}</p><div className="loading-grid">{[0,1,2].map(i => <div key={i} />)}</div></main>; }
