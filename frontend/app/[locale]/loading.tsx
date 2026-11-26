import { getDictionary } from './dictionaries';

export default async function Loading() {
  const dict = await getDictionary();
  return <main id="main" className="loading-shell" aria-busy="true" aria-label={dict.ui.loading}>
    <div className="loading-heading" aria-hidden="true"><span /><span /></div>
    <div className="loading-grid" aria-hidden="true">{[0, 1, 2].map(i => <div key={i} />)}</div>
  </main>;
}
