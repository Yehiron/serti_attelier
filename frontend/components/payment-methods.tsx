/** Card brands accepted through Wompi, drawn locally as small card-shaped badges (no remote assets). */
function Visa() {
  return <svg role="img" aria-label="Visa" viewBox="0 0 48 30"><title>Visa</title><rect width="48" height="30" rx="4" fill="#fff" /><text x="24" y="20" textAnchor="middle" fill="#1a1f71" fontSize="13.5" fontWeight="800" fontStyle="italic" letterSpacing="-.4" fontFamily="Arial, Helvetica, sans-serif">VISA</text><rect x="9" y="23" width="30" height="1.6" rx=".8" fill="#f7b600" /></svg>;
}
function Mastercard() {
  return <svg role="img" aria-label="Mastercard" viewBox="0 0 48 30"><title>Mastercard</title><defs><clipPath id="mc-left"><circle cx="19.5" cy="15" r="9" /></clipPath></defs><rect width="48" height="30" rx="4" fill="#fff" /><circle cx="19.5" cy="15" r="9" fill="#eb001b" /><circle cx="28.5" cy="15" r="9" fill="#f79e1b" /><circle cx="28.5" cy="15" r="9" fill="#ff5f00" clipPath="url(#mc-left)" /></svg>;
}
function Amex() {
  return <svg role="img" aria-label="American Express" viewBox="0 0 48 30"><title>American Express</title><rect width="48" height="30" rx="4" fill="#016fd0" /><rect x="3.5" y="3.5" width="41" height="23" rx="2" fill="none" stroke="#fff" strokeOpacity=".35" strokeWidth=".8" /><g fill="#fff" fontFamily="Arial, Helvetica, sans-serif" fontWeight="800" textAnchor="middle"><text x="24" y="14" fontSize="7" letterSpacing=".6">AMERICAN</text><text x="24" y="22" fontSize="7" letterSpacing=".9">EXPRESS</text></g></svg>;
}
export function PaymentMethods({ label }: { label: string }) {
  return <div className="payment-methods"><p className="eyebrow">{label}</p><div><Visa /><Mastercard /><Amex /></div></div>;
}
