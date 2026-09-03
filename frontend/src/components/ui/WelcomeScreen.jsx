import { ArrowRight, ShieldCheck, Scissors, Package } from 'lucide-react';

/**
 * The first thing the app opens on.
 *
 * On the web the product has a front door -- the marketing site at `/`, which
 * the workspace's "Back to Home" button links to. The Android build bundles
 * only the workspace, so it opened straight onto a login form: no name, no
 * explanation, and a "Back to Home" button that pointed at a page which is not
 * in the bundle.
 *
 * This is that missing front door, and it is deliberately not a copy of the
 * marketing site. Someone who has installed the app has already been sold to.
 * What they need is to know they are in the right place and to get to their
 * work in one tap.
 *
 * The animation is CSS only -- three staggered fade-and-rise steps -- so it
 * costs no library and cannot jank a low-end phone the way an animation loop
 * can. It also respects prefers-reduced-motion, which on a phone is a setting
 * people turn on because motion makes them ill, not a preference to style
 * around.
 */
export function WelcomeScreen({ onSignIn, onCreateAccount }) {
  return (
    <div className="welcome-screen">
      <div className="welcome-inner">
        <div className="welcome-mark welcome-step" style={{ '--step': 0 }}>
          <img src="/icon-512.png" alt="" width="72" height="72" />
        </div>

        <div className="welcome-step" style={{ '--step': 1 }}>
          <h1 className="welcome-title">SCALEEZY</h1>
          <p className="welcome-tagline">YOUR VISION. OUR CRAFT.</p>
        </div>

        <p className="welcome-lede welcome-step" style={{ '--step': 2 }}>
          Your boutique&rsquo;s workspace — orders, measurements, the production
          floor and your design library, on the shop floor with you.
        </p>

        <ul className="welcome-points welcome-step" style={{ '--step': 3 }}>
          <li><Scissors size={15} /> Track every garment from measurement to delivery</li>
          <li><Package size={15} /> Fabric and trim stock that keeps itself honest</li>
          <li><ShieldCheck size={15} /> Each boutique&rsquo;s data stays its own</li>
        </ul>

        <div className="welcome-actions welcome-step" style={{ '--step': 4 }}>
          <button type="button" className="welcome-primary" onClick={onSignIn}>
            Sign in <ArrowRight size={16} />
          </button>
          <button type="button" className="welcome-secondary" onClick={onCreateAccount}>
            Create a boutique account
          </button>
        </div>
      </div>
    </div>
  );
}
