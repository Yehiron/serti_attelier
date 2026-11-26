'use client';

/**
 * The contact letter folded in three and closed with gold wax.
 * mode "fold": absolute overlay inside the form that folds the real letter.
 * mode "static": the finished, sealed letter shown above the thanks message.
 */
export function SealedLetter({ mode, onComplete }: { mode: 'fold' | 'static'; onComplete?: () => void }) {
  return <div className={`letter-fold letter-fold--${mode}`} aria-hidden="true">
    <div className="letter-fold-panel letter-fold-top"><div className="letter-face letter-face-front" /><div className="letter-face letter-face-back"><div className="letter-fold-flap" /></div></div>
    <div className="letter-fold-panel letter-fold-middle"><div className="letter-face letter-face-front" /></div>
    <div className="letter-fold-panel letter-fold-bottom"><div className="letter-face letter-face-front" /><div className="letter-face letter-face-back" /></div>
    <div className="wax-seal" onAnimationEnd={event => { if (event.animationName === 'wax-press') onComplete?.(); }}>
      <svg viewBox="0 0 120 120" aria-hidden="true">
          <defs>
            <radialGradient id="wax-gold" cx="35%" cy="28%" r="75%"><stop stopColor="#f8df91" /><stop offset=".36" stopColor="#e9c46a" /><stop offset=".72" stopColor="#c9a14a" /><stop offset="1" stopColor="#8a6a22" /></radialGradient>
          </defs>
          <path fill="url(#wax-gold)" stroke="#92712b" strokeWidth="1.5" d="M60 5 C67 2 72 8 78 8 C85 6 88 13 94 15 C101 16 101 23 106 28 C112 32 110 39 113 45 C117 51 113 57 115 63 C116 70 110 74 109 81 C108 88 101 90 98 96 C95 102 88 101 82 106 C77 111 70 108 64 113 C57 116 52 111 45 112 C39 112 35 106 28 105 C21 103 20 96 15 92 C10 88 11 81 8 75 C4 69 8 63 5 57 C3 50 8 45 8 39 C9 32 16 29 18 23 C22 17 29 18 34 13 C40 9 46 12 52 7 C55 5 58 6 60 5 Z" />
          <circle cx="60" cy="60" r="39" fill="none" stroke="#fff0b1" strokeOpacity=".45" strokeWidth="2" />
          <circle cx="60" cy="61" r="35" fill="#9b762b" fillOpacity=".16" stroke="#82601c" strokeOpacity=".35" />
        </svg>
      <span className="wax-seal-mark" /><span className="wax-seal-shine" />
    </div>
  </div>;
}
