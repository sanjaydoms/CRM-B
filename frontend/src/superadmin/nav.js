/**
 * The console's navigation, as data.
 *
 * One list rather than markup, because three things read it: the nav rail, the
 * router's screen lookup, and the "unknown route" fallback. When those drifted
 * apart in the boutique workspace the desktop and mobile menus ended up
 * disagreeing about which screens exist (frontend/src/App.jsx nav vs
 * BottomNavigation) -- worth not repeating.
 *
 * `absent: true` marks a screen the specification asks for that this product
 * has no data behind. It is still listed and still reachable: the screen
 * explains what is missing and why, which is more useful than a menu with a
 * hole in it where someone expected an item. See core/modules.py for the
 * server-side equivalent of the same decision.
 */

import {
  Activity, AlertTriangle, Building2, FileWarning, Flag, Gauge, HeartPulse,
  KeyRound, LayoutDashboard, Mail, Plug, PackageSearch, ScrollText, Settings,
  ShoppingBag, Sparkles, Users, Wrench,
} from 'lucide-react';

export const NAV = [
  {
    group: 'Overview',
    items: [
      { key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { key: 'health', label: 'System Health', icon: HeartPulse },
    ],
  },
  {
    group: 'Organizations',
    items: [
      { key: 'boutiques', label: 'Boutiques', icon: Building2 },
      { key: 'users', label: 'Users', icon: Users },
      { key: 'onboarding', label: 'Onboarding', icon: Sparkles },
      { key: 'leads', label: 'Leads', icon: Mail },
    ],
  },
  {
    group: 'Product',
    items: [
      { key: 'modules', label: 'Modules', icon: PackageSearch },
      { key: 'flags', label: 'Feature Flags', icon: Flag },
      { key: 'config', label: 'Configuration', icon: Settings },
    ],
  },
  {
    group: 'Operations',
    items: [
      { key: 'orders', label: 'Orders Monitor', icon: ShoppingBag },
      { key: 'integrations', label: 'Integrations', icon: Plug },
      { key: 'messaging', label: 'Customer Messaging', icon: Activity },
    ],
  },
  {
    group: 'Reliability',
    items: [
      { key: 'errors', label: 'Error Center', icon: FileWarning, badge: 'errors' },
      { key: 'jobs', label: 'Jobs & Queues', icon: Gauge, absent: true },
      { key: 'api', label: 'API Monitoring', icon: AlertTriangle, absent: true },
    ],
  },
  {
    group: 'Security',
    items: [
      { key: 'audit', label: 'Audit Log', icon: ScrollText },
      { key: 'sessions', label: 'Sessions & Tokens', icon: KeyRound },
    ],
  },
  {
    group: 'Support',
    items: [
      { key: 'support', label: 'Diagnostics', icon: Wrench },
    ],
  },
];

/** Every routable key, for the unknown-route check. */
export const ROUTES = new Set(NAV.flatMap((g) => g.items.map((i) => i.key)));

export const labelFor = (key) => {
  for (const group of NAV) {
    for (const item of group.items) if (item.key === key) return item.label;
  }
  return key;
};
