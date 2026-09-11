import React, { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { 
  Users, ShoppingBag, Scissors, Search, 
  Upload, Check, ArrowRight, ArrowLeft, Heart, 
  MessageSquare, Star, Copy, ShieldCheck, Compass, BarChart2,
  FolderOpen, Sparkles, HelpCircle, X, ExternalLink,
  ChevronRight, Lock, Mail, Phone, Calendar, Landmark, 
  FileText, Bell, User, MapPin, Eye, EyeOff, Edit2, Plus, Trash2, LogOut, History, Package, Menu,
  PenTool, Settings, RotateCw, Clock, Wallet,
  Shirt, TrendingUp, AlertCircle, CalendarDays, LayoutGrid, List, Receipt, Banknote,
  Truck, PackageCheck, CheckCircle2, Boxes, Crown, ShoppingCart, Coins, ClipboardList,
  Type, Tag, Layers, Palette, IndianRupee, Link as LinkIcon, Image as ImageIcon, Save,
  Play, Pause, SkipForward, RefreshCw, Ruler, Target, Leaf, Building2, Globe, Camera, Store,
  PanelLeftClose, PanelLeftOpen
} from 'lucide-react';
import { api } from './services/api';
import { resolveMediaUrl } from './services/media';
import {
  formatMoney, formatDate as fmtDate, formatDateTime as fmtDateTime,
  formatTime as fmtTime, setBoutiqueTimeZone, orderRef,
} from './services/format';
// The inventory panel and the design studio are whole screens behind their own
// tabs, and together they are a sixth of the bundle. Loading them eagerly made
// every first paint -- including the login screen -- wait on code most sessions
// never open, so they are fetched when their tab is first shown instead.
// TemplateForm stays eager: it renders inline in the order wizard, where a
// loading flicker mid-form would be worse than its few KB.
const GarmentPartPicker = lazy(() => import('./features/designStudio/GarmentPartPicker'));
const GarmentFabricPicker = lazy(() => import('./features/fabrics/GarmentFabricPicker'));
const FabricColorFilter = lazy(() => import('./features/fabrics/FabricColorFilter'));
import { fabricMatchesColour } from './features/fabrics/colour';
// Named export off the same module, so it arrives with the chunk the
// pickers already load rather than costing a second request.
const SelectedDesignSummary = lazy(() => import('./features/designStudio/GarmentPartPicker')
  .then(m => ({ default: m.SelectedDesignSummary })));
const InventoryPanel = lazy(() => import('./features/inventory/InventoryPanel'));
const DesignLibrary = lazy(() => import('./features/designStudio/DesignLibrary'));
const DesignDashboard = lazy(() => import('./features/designStudio/DesignDashboard'));
const DesignWork = lazy(() => import('./features/designStudio/DesignWork'));
const StaffPanel = lazy(() => import('./features/staff/StaffPanel'));
const AlterationsPanel = lazy(() => import('./features/alterations/AlterationsPanel'));
const FinancePanel = lazy(() => import('./features/finance/FinancePanel'));
import TemplateForm from './features/catalog/TemplateForm';
import GarmentSummary from './features/catalog/GarmentSummary';
import DesignCataloguePicker from './features/designStudio/DesignCataloguePicker';
import GarmentSelectionsReview from './features/catalog/GarmentSelectionsReview';
import OrderAlterations from './features/alterations/OrderAlterations';
import AlterationList from './features/alterations/AlterationList';
import OrderGarmentBrief from './features/catalog/OrderGarmentBrief';
import OrderKanban from './features/orders/OrderKanban';
import FabricGroup from './features/fabrics/FabricGroup';
import { blankGroup, blankMaterial, useFabricTaxonomy } from './features/fabrics/taxonomy';
import { MobileHeader } from './components/ui/MobileHeader';
import {
  PageHeader, StatCard, SectionCard, Chips, AvatarInitials, ProgressBar, SearchBox, Segmented, IconTile,
  FormModal, Field, Dropzone, PhotoTile, AddMoreTile, InfoNote, FormSection,
} from './components/ui/Atelier';
import { useLanguage } from './i18n/LanguageContext.jsx';
import LanguageSelector from './components/LanguageSelector.jsx';
import SettingsPage from './components/SettingsPage.jsx';
import { InvoiceRenderer, normalizeInvoiceData } from './components/invoice/InvoiceTemplates';
import { BottomNavigation } from './components/ui/BottomNavigation';

import { BottomSheet } from './components/ui/BottomSheet';
import { ResponsiveCard } from './components/ui/ResponsiveCard';
import { ProgressiveAccordion } from './components/ui/ProgressiveAccordion';
import DressesDropdown from './components/ui/DressesDropdown';
import GarmentPairingModal, { getGarmentPairConfig } from './components/ui/GarmentPairingModal';

/** Placeholder shown while a lazily loaded screen arrives. */
// Whole-rupee money for the dashboard, Indian digit grouping. Paise are
// noise at a glance; the detail screens keep them.
const inr = (n) => `₹${Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

// One avatar for every user surface. Shows the person's uploaded photo when
// they have one, otherwise their initial on a filled circle -- never the stock
// stranger that used to be hardcoded here. Fills whatever circle wraps it.
const UserAvatar = ({ user, size }) => {
  const url = resolveMediaUrl(user?.profile_photo || '');
  const initial = (user?.first_name || user?.name || user?.email || 'U').trim().charAt(0).toUpperCase();
  const box = size ? { width: size, height: size } : { width: '100%', height: '100%' };
  if (url) {
    return <img src={url} alt="" style={{ ...box, borderRadius: '50%', objectFit: 'cover' }} />;
  }
  return (
    <div style={{ ...box, borderRadius: '50%', display: 'flex', alignItems: 'center',
                  justifyContent: 'center', background: '#0f291e', color: '#fff',
                  fontWeight: 600, fontSize: size ? size * 0.42 : '1em' }}>
      {initial}
    </div>
  );
};

// Customer value tier, as one pill. VIP and high-value carry their brand
// colours; everyone else gets a neutral badge. One component so the directory
// card and the profile banner cannot drift apart.
const SEGMENT_TONES = {
  // fg is a darker brass than --accent-text (#986a26) so 11px badge text clears
  // WCAG AA (~4.9:1) on the --accent-color tint; bg/bd use the accent tokens.
  VIP: { bg: 'var(--accent-color)', fg: '#7d6216', bd: 'var(--accent-border)' },
  HVC: { bg: '#efe9f7', fg: '#6b3fa0', bd: '#dcc9ee' },
};
const SegmentBadge = ({ segment }) => {
  if (!segment) return null;
  const tone = SEGMENT_TONES[segment];
  const skin = tone
    ? { background: tone.bg, color: tone.fg, border: `1px solid ${tone.bd}` }
    : { background: 'var(--surface-inset)', color: 'var(--text-secondary)', border: '1px solid var(--border-color)' };
  return (
    <span style={{
      fontSize: 'var(--text-2xs)', fontWeight: 'var(--weight-bold)', letterSpacing: '0.06em',
      padding: '2px 8px', borderRadius: '999px', textTransform: 'uppercase', ...skin,
    }}>{segment}</span>
  );
};

// The AI "Style Profile" card. Deep-forest hero surface with gold accents --
// the same emphasis treatment as the dashboard revenue hero -- so a premium
// insight reads as special without dropping a black card onto the light page.
// Was two near-identical dark (#141414/#0d0d0d) blocks, one on the directory
// card and one on the profile detail; now one component. Shows only fields the
// AI actually filled -- the old detail card printed fabricated demo figures
// ("premium designer", "Charcoal Black 90%") for every customer with no
// style_dna, which read as real client data.
const StyleProfileCard = ({ customer }) => {
  const dna = customer?.style_dna || {};
  const rows = [
    ['Budget', dna.budget, Wallet], ['Colours', dna.colors, Palette], ['Style', dna.style, Shirt],
    ['Size', dna.size, Ruler], ['Visit pattern', dna.visit_pattern, CalendarDays],
  ].filter(([, v]) => v);
  const riskColor = dna.risk_level === 'danger' ? 'var(--danger-color)'
    : dna.risk_level === 'warning' ? 'var(--warning-color)' : 'var(--success-color)';
  // "Dusty Rose 60% Ivory 30% Gold 10%" -> a swatch per named colour, read
  // through the same name-to-shade map the fabric cards use.
  const swatches = typeof dna.colors === 'string'
    ? dna.colors.split(/\d+%/).map((n) => n.trim()).filter(Boolean) : [];
  const hasAny = rows.length || dna.risk_status || dna.next_action;
  return (
    <SectionCard icon={Sparkles} tone="amber"
                 title={customer?.first_name ? `${customer.first_name}'s style profile` : 'Style Profile'}>
      {!hasAny && (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>No AI style profile for this customer yet.</div>
      )}
      {rows.map(([label, value, Icon]) => (
        <div key={label} className="at-dna-row">
          <span className="at-dna-label"><Icon size={16} /> {label}</span>
          <strong>
            {label === 'Colours' && swatches.length > 0 && (
              <span className="at-swatches">
                {swatches.map((name) => <i key={name} title={name} style={{ background: getColorCircleStyle(name) }} />)}
              </span>
            )}
            {value}
          </strong>
        </div>
      ))}
      {dna.risk_status && (
        <div className="at-dna-row">
          <span className="at-dna-label"><ShieldCheck size={16} /> Risk status</span>
          <strong style={{ color: riskColor, display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: riskColor }} />
            {dna.risk_status}
          </strong>
        </div>
      )}
      {dna.next_action && (
        <div className="at-dna-row">
          <span className="at-dna-label"><Target size={16} /> Next action</span>
          <strong style={{ color: 'var(--accent-text)', fontStyle: 'italic' }}>&ldquo;{dna.next_action}&rdquo;</strong>
        </div>
      )}
      {hasAny && (
        <InfoNote tone="green" icon={Leaf} style={{ marginTop: 'var(--space-3)', padding: '10px 14px' }}>
          <em>Read automatically from your sales data — not entered by hand.</em>
        </InfoNote>
      )}
    </SectionCard>
  );
};

// Live date + time for the dashboard header. Ticks once a minute -- seconds add
// motion nobody reads and a re-render every second for no reason.
const HeaderClock = () => {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(id);
  }, []);
  const date = now.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return (
    <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
      {date} · <b style={{ color: 'var(--text-primary)' }}>{time}</b>
    </span>
  );
};

const ScreenLoading = () => (
  <div style={{ padding: '48px', textAlign: 'center', color: '#8a8a8a' }}>Loading...</div>
);
import { splitSpec, validateSpec } from './services/templates';

// Mirrors core/permissions.py SUPERVISOR_ROLES. Roles that run the floor and
// may hand work to someone else. A list rather than a bare === 'Master' check
// so a boutique that splits its floor into specialists can be added in one
// place instead of hunting every comparison.
const SUPERVISOR_ROLES = ['Master'];

// Everyone who works on garments. resolve_user_role returns the Tailor
// profile's role verbatim, so a boutique that has split its floor produces
// role strings beyond 'Tailor' and 'Master' -- and get_default_workflow
// permits each of them on a specific stage. Comparing against the two literal
// names stranded every specialist: routed to a tab their own nav does not
// contain, and shown an order's money that the permission matrix says
// production staff must not see.
const PRODUCTION_ROLES = [
  'Tailor', 'Master', 'Maggam Master', 'Karigar', 'Packaging Staff', 'QC Staff',
];
const isProductionStaff = (role) => PRODUCTION_ROLES.includes(role);

/**
 * A stored mobile number, written the way its owner would recognise it.
 *
 * Numbers are now stored canonically -- Customer.save folds "+91 (0) 98765
 * 43211", "0091 9876543211" and "098765 43211" onto one value -- so that a
 * returning client is the same record rather than a second profile. The stored
 * form is 919876543211, which is right for identity and wrong for a human: it
 * was printing on the invoice, and three screens rendered "+91 919876543211"
 * by prefixing a country code the value already carried.
 *
 * Storage is canonical; display is formatted. Anything that is not a
 * recognisable Indian number is shown exactly as it was typed, because those
 * digits are the only record of how to reach that client.
 */
const formatMobile = (raw) => {
  const digits = String(raw || '').replace(/\D/g, '');
  if (digits.length === 12 && digits.startsWith('91')) {
    const n = digits.slice(2);
    return `+91 ${n.slice(0, 5)} ${n.slice(5)}`;
  }
  if (digits.length === 10) return `${digits.slice(0, 5)} ${digits.slice(5)}`;
  return raw || '';
};

/**
 * wa.me wants digits only, with the country code and no punctuation.
 *
 * Built as `wa.me/91${mobile}` at the call site, which produced
 * wa.me/91+91 98765 43211 for any number the owner had typed with formatting --
 * and, once numbers were stored canonically, wa.me/91919876543211. Both open a
 * chat with nobody. The stored value already carries the country code.
 */
const waLink = (raw) => `https://wa.me/${String(raw || '').replace(/\D/g, '')}`;


// Mirrors Appointment.TYPE_CHOICES in apps/scheduling/models.py.
// Mirrors Appointment.STATUS_CHOICES in apps/scheduling/models.py.
const APPOINTMENT_STATUS_LABELS = {
  SCHEDULED: 'Scheduled',
  CONFIRMED: 'Confirmed',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  RESCHEDULED: 'Rescheduled',
};

const APPOINTMENT_TYPE_LABELS = {
  CONSULTATION: 'Design Consultation',
  MEASUREMENT: 'Measurement Fitting',
  TRIAL: 'Garment Trial',
  DELIVERY: 'Final Delivery',
};

// Mirrors Tailor.ROLE_CHOICES. A boutique run by one generalist keeps using Master;
// larger studios split the work, and each stage only accepts its own specialists.
const STAFF_ROLES = [
  { value: 'Tailor', label: 'Stitching Tailor', hint: 'Stitches the garment.' },
  { value: 'Master', label: 'Master Tailor (generalist)', hint: 'Can work on every stage.' },
  { value: 'Maggam Master', label: 'Maggam Master', hint: 'Runs embroidery before stitching.' },
  { value: 'Karigar', label: 'Karigar', hint: 'Handwork on the frame, alongside the Maggam Master.' },
  { value: 'Packaging Staff', label: 'Packaging Staff', hint: 'Packs the garment before dispatch.' },
  { value: 'QC Staff', label: 'QC Staff', hint: 'Runs the quality inspection.' },
];

const GARMENT_PRICES = {
  'Lehenga': 32000,
  'Gown': 25000,
  'Saree': 15000,
  'Anarkali': 18000,
  'Kurti': 5000,
  'Sherwani': 35000,
  'Suit': 22000
};

const DEFAULT_CUSTOMER_DATA = {
  first_name: '',
  last_name: '',
  mobile_number: '',
  email_address: '',
  address: '',
  city_region: '',
  source: 'Walk In',
  customer_type: 'Women',
  garment_type: 'Lehenga',
  neckline_style: '',
  sleeve_style: '',
  back_style: '',
  length_preference: '',
  silhouette: '',
  embellishments: '',
  pattern_style: '',
  occasion: '',
  custom_requirements: '',
  date_of_birth: '',
  occupation: '',
  preferred_communication: 'WhatsApp',
  notes: '',
  measurements: {
    bust: '',
    waist: '',
    hips: '',
    shoulder: '',
    arm_length: '',
    neck: '',
    length: ''
  }
};

const getColorCircleStyle = (colorName) => {
  if (!colorName) return '#fbeedb';
  const name = colorName.toLowerCase();
  if (name.includes('rose') || name.includes('pink')) return '#e2a3a1';
  if (name.includes('gold')) return '#d4af37';
  if (name.includes('black') || name.includes('charcoal')) return '#2e2e2e';
  if (name.includes('blue')) return '#4169e1';
  if (name.includes('green') || name.includes('olive')) return '#556b2f';
  if (name.includes('maroon') || name.includes('red')) return '#800000';
  if (name.includes('white') || name.includes('cream')) return '#fafafa';
  return '#fbeedb';
};

// A garment template key as a person reads it: blouse_length -> "Blouse length".
// Shared by the staff blueprint panel and the stage-detail "What to make" block,
// which were about to grow two different versions of the same line.
const humaniseSpecKey = (key) => {
  const words = String(key).replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

// Every garment on an order, for screens that only need to name them.
// Prefers the order's garment jobs -- the record of what was actually ordered --
// and falls back to the customer's single garment_type only for orders written
// before garment jobs existed. Mirrors domains/orders/garments.py; the API sends
// `garments` already, so this is the client-side guard for older payloads.
const orderGarmentNames = (order) => {
  if (!order) return [];
  if (Array.isArray(order.garments) && order.garments.length) return order.garments;
  const jobs = order.garment_jobs || [];
  if (jobs.length) return jobs.map(j => j.template_name || j.template_key || 'Custom garment');
  return order.customer_garment_type ? [order.customer_garment_type] : [];
};

const orderGarmentLabel = (order) => {
  const names = orderGarmentNames(order);
  if (!names.length) return 'Custom garment';
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
};

const getVisibleMeasurementFields = (stitchParts) => {
  const allFields = ['bust', 'waist', 'hips', 'shoulder', 'arm_length', 'neck', 'length'];
  if (!stitchParts || stitchParts.length === 0) return allFields;
  
  const hasUpper = stitchParts.some(p => ['Blouse', 'Blouse / Choli', 'Kurta / Kameez', 'Sherwani Top', 'Anarkali Dress', 'Gown Body', 'Kurti Top'].includes(p));
  const hasLower = stitchParts.some(p => ['Skirt', 'Salwar / Bottom', 'Pants / Churidar', 'Bottom Churidar', 'Petticoat'].includes(p));
  
  const fields = [];
  if (hasUpper) {
    fields.push('bust', 'shoulder', 'arm_length', 'neck');
  }
  if (hasLower) {
    fields.push('hips');
  }
  if (hasUpper || hasLower) {
    fields.push('waist', 'length');
  }
  
  return allFields.filter(f => fields.includes(f));
};

const getTailorAvatarUrl = (name) => {
  if (!name) return '';
  const n = name.toLowerCase();
  if (n.includes('rohit')) return 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150';
  if (n.includes('anya')) return 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150';
  if (n.includes('rahul')) return 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150';
  if (n.includes('preeti')) return 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150';
  return 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=150';
};

const getTailorTags = (name) => {
  if (!name) return [];
  const n = name.toLowerCase();
  if (n.includes('rohit')) return ['Ethnic Wear', 'Sherwani', 'Indo-Western'];
  if (n.includes('anya')) return ['Ethnic Wear', 'Lehenga', 'Blouse'];
  if (n.includes('rahul')) return ['Gown', 'Suit', 'Formal Wear'];
  if (n.includes('preeti')) return ['Embroidery', 'Zardozi', 'Artisan'];
  return ['Custom', 'Tailoring'];
};

// Clickable twelve-stage timeline. Shown on the owner's order registry and on a
// master's assignments board, so it lives here rather than being written twice.
/** The customer messages an order has raised, and the owner's send button.
 *
 * There is no WhatsApp Business integration behind this. Each queued message
 * carries a wa.me link that opens the customer's chat with the text already
 * written; the owner sends it from their own number and then marks it sent.
 * Nothing here can observe a send that happened in another app, so "Mark sent"
 * is the owner's word for it, which is why it is a separate deliberate click
 * rather than something inferred from opening the link.
 *
 * Presentational: the queue is fetched once for the whole screen by
 * fetchDashboardAndConfig and handed down. It used to fetch its own messages
 * from the order id, which was tidier to drop in and wrong twice over -- one
 * request per order card on an unpaginated registry, and a list that never
 * refreshed, so a message queued by the status dropdown directly above it
 * stayed invisible until a hard reload.
 */
function CustomerMessageQueue({ orderId, messages, onMarkSent }) {
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState(null);

  const markSent = async (messageId) => {
    setBusyId(messageId);
    setError(null);
    try {
      await onMarkSent(orderId, messageId);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  if (!messages.length && !error) return null;

  const queued = messages.filter((m) => m.status === 'QUEUED');

  return (
    <div style={{
      margin: '8px 0', padding: '12px 16px', background: 'var(--surface-color)',
      borderRadius: '8px', border: '1px solid var(--border-color)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
        <MessageSquare size={14} />
        <span style={{ fontSize: '13px', fontWeight: 600 }}>Customer updates</span>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          {queued.length} waiting to send
        </span>
      </div>

      {error && (
        <div style={{ fontSize: '12px', color: 'var(--danger-color, #b3261e)', marginBottom: '8px' }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {messages.map((message) => (
          <div key={message.id} style={{
            display: 'flex', alignItems: 'flex-start', gap: '12px',
            padding: '10px', borderRadius: '6px',
            border: '1px solid var(--border-color)',
            opacity: message.status === 'QUEUED' ? 1 : 0.6
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '2px' }}>
                {message.template_key.replace(/_/g, ' ')} &middot; {message.to_number}
                {message.status !== 'QUEUED' && ` · ${message.status.toLowerCase()}`}
                {message.sent_by_name && ` by ${message.sent_by_name}`}
              </div>
              <div style={{ fontSize: '13px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {message.body}
              </div>
            </div>

            {message.status === 'QUEUED' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flexShrink: 0 }}>
                {message.whatsapp_url ? (
                  <a
                    href={message.whatsapp_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary"
                    style={{ fontSize: '12px', padding: '6px 10px', whiteSpace: 'nowrap', textAlign: 'center' }}
                  >
                    Open WhatsApp
                  </a>
                ) : (
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                    No mobile number
                  </span>
                )}
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ fontSize: '12px', padding: '6px 10px', whiteSpace: 'nowrap' }}
                  disabled={busyId === message.id}
                  onClick={() => markSent(message.id)}
                >
                  {busyId === message.id ? 'Saving…' : 'Mark sent'}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

const GARMENT_VIEWS = [
  ['FRONT', 'Front view'], ['BACK', 'Back view'],
  ['LEFT', 'Left side'], ['RIGHT', 'Right side'],
  ['DETAIL', 'Close-up detail'], ['FABRIC', 'Fabric texture'],
  ['SLEEVE', 'Sleeve detail'], ['BLOUSE', 'Blouse detail'],
  ['DUPATTA', 'Dupatta styling'],
];

/** Photographs of the finished garment, and the decision to show the customer.
 *
 * Front and back are required before publishing, because those are the two the
 * specification promises the customer. Publishing queues the "your outfit is
 * ready" message, so it is a deliberate button rather than something that
 * happens the moment a photograph lands -- the angles go up one at a time, and
 * a half-uploaded gallery is not what anyone wants sent.
 *
 * The images come from the order payload that is already on screen, so this
 * costs no extra request.
 */
function GarmentGallery({ order, onChanged }) {
  const { t } = useLanguage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [view, setView] = useState('FRONT');
  const fileRef = useRef(null);
  const cameraRef = useRef(null);

  const images = order.garment_images || [];
  const published = order.garment_images_published;
  const have = new Set(images.map((i) => i.view));
  const missing = ['FRONT', 'BACK'].filter((v) => !have.has(v));

  const run = async (work) => {
    setBusy(true);
    setError(null);
    try {
      await work();
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const onPick = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    run(() => api.uploadGarmentImage(order.id, view, file));
    event.target.value = '';
  };

  return (
    <div style={{
      margin: '8px 0', padding: '12px 16px', background: 'var(--surface-color)',
      borderRadius: '8px', border: '1px solid var(--border-color)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px', flexWrap: 'wrap' }}>
        <Package size={14} />
        <span style={{ fontSize: '13px', fontWeight: 600 }}>{t('ordersPage.finishedGarmentPhotos', 'Finished garment photos')}</span>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          {published ? t('ordersPage.visibleToCustomer', 'visible to the customer') : t('ordersPage.uploadedNotShared', '{count} uploaded, not yet shared', { count: images.length })}
        </span>
      </div>

      {error && (
        <div style={{ fontSize: '12px', color: 'var(--danger-color, #b3261e)', marginBottom: '8px' }}>
          {error}
        </div>
      )}

      {images.length > 0 && (
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '10px' }}>
          {images.map((image) => (
            <figure key={image.id} style={{ margin: 0, width: '90px' }}>
              <img
                src={resolveMediaUrl(image.image)}
                alt={image.view_label}
                style={{
                  width: '90px', height: '120px', objectFit: 'cover',
                  borderRadius: '6px', border: '1px solid var(--border-color)'
                }}
              />
              <figcaption style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {image.view_label}
              </figcaption>
              <button
                type="button"
                onClick={() => run(() => api.deleteGarmentImage(order.id, image.id))}
                disabled={busy}
                style={{
                  fontSize: '10px', padding: '2px 6px', marginTop: '2px',
                  background: 'none', border: '1px solid var(--border-color)',
                  borderRadius: '4px', cursor: 'pointer', width: '100%'
                }}
              >
                {t('ordersPage.remove', 'Remove')}
              </button>
            </figure>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <select
          className="form-control"
          style={{ fontSize: '12px', padding: '6px 10px', width: 'auto', margin: 0 }}
          value={view}
          onChange={(e) => setView(e.target.value)}
          disabled={busy}
        >
          {GARMENT_VIEWS.map(([value, label]) => (
            <option key={value} value={value}>{label}{have.has(value) ? ' (replace)' : ''}</option>
          ))}
        </select>

        <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPick} />
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={onPick} />
        <button
          type="button"
          className="btn-secondary"
          style={{ fontSize: '12px', padding: '6px 10px' }}
          disabled={busy}
          onClick={() => cameraRef.current?.click()}
        >
          {busy ? 'Working…' : '📷 Take photo'}
        </button>
        <button
          type="button"
          className="btn-secondary"
          style={{ fontSize: '12px', padding: '6px 10px' }}
          disabled={busy}
          onClick={() => fileRef.current?.click()}
        >
          {busy ? 'Working…' : t('common.chooseFromGallery', 'Choose from gallery')}
        </button>

        <button
          type="button"
          className="btn-secondary"
          style={{ fontSize: '12px', padding: '6px 10px' }}
          disabled={busy || (!published && missing.length > 0)}
          title={missing.length ? `Still needs: ${missing.join(', ')}` : ''}
          onClick={() => run(() => api.publishGarmentImages(order.id, !published))}
        >
          {published ? 'Hide from customer' : t('ordersPage.shareWithCustomer', 'Share with customer')}
        </button>

        {!published && missing.length > 0 && (
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            {t('ordersPage.needsFrontAndBack', 'needs front and back')}
          </span>
        )}
      </div>
    </div>
  );
}

function StageTimeline({ stages, onSelectStage }) {
  const { t } = useLanguage();
  // Fifteen stages in a strip about three-and-a-half stages wide: opening an
  // order on a phone put "Created" on screen and whatever actually needs doing
  // several swipes away. Centre the live stage (or the last one finished) so
  // the strip opens where the work is.
  const activeRef = React.useRef(null);
  const scrollerRef = React.useRef(null);
  React.useEffect(() => {
    const el = activeRef.current, box = scrollerRef.current;
    if (!el || !box) return;
    // Not scrollIntoView: it would also scroll the page vertically to reach a
    // strip the user may not have scrolled to yet.
    box.scrollLeft = el.offsetLeft - (box.clientWidth - el.offsetWidth) / 2;
  }, [stages]);

  const activeIndex = (() => {
    if (!stages || !stages.length) return -1;
    const running = stages.findIndex(
      (s) => s.status === 'IN_PROGRESS' || s.status === 'PAUSED');
    if (running !== -1) return running;
    let last = -1;
    stages.forEach((s, i) => { if (s.status === 'COMPLETED') last = i; });
    return last;
  })();

  if (!stages || stages.length === 0) {
    return (
      <div style={{
        margin: '8px 0', padding: '12px 16px', background: 'var(--surface-color)',
        borderRadius: '8px', border: '1px solid var(--border-color)',
        fontSize: '12px', color: 'var(--text-muted)', textAlign: 'center'
      }}>
        {t('ordersPage.noProductionStages', 'No production stages recorded for this order.')}
      </div>
    );
  }

  return (
    <div ref={scrollerRef} style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      margin: '8px 0', padding: '12px 16px', background: 'var(--surface-color)',
      borderRadius: '8px', border: '1px solid var(--border-color)',
      overflowX: 'auto', gap: '4px'
    }}>
      {stages.map((stage, idx, arr) => {
        const isCompleted = stage.status === 'COMPLETED';
        const isInProgress = stage.status === 'IN_PROGRESS';
        const isPaused = stage.status === 'PAUSED';
        const isSkipped = stage.status === 'SKIPPED';

        let statusColor = 'var(--border-color)';
        if (isCompleted) statusColor = '#10b981';
        else if (isInProgress) statusColor = '#3b82f6';
        else if (isPaused) statusColor = '#f59e0b';
        else if (isSkipped) statusColor = '#9ca3af';

        return (
          <div
            key={stage.id || stage.stage_key}
            ref={idx === activeIndex ? activeRef : null}
            role="button"
            tabIndex={0}
            title={`${stage.stage_name} — ${stage.status.replace('_', ' ').toLowerCase()}`}
            style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: '108px', cursor: 'pointer', padding: '4px 0' }}
            onClick={() => onSelectStage(stage)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectStage(stage); } }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px', flex: '0 0 88px', width: '88px' }}>
              <div style={{
                width: '10px', height: '10px', borderRadius: '50%',
                backgroundColor: statusColor,
                border: isInProgress ? '2px solid #fff' : 'none',
                boxShadow: isInProgress ? '0 0 0 2px #3b82f6' : 'none'
              }} />
              <span style={{
                fontSize: '10px',
                lineHeight: 1.25,
                fontWeight: isInProgress ? 700 : 500,
                color: isCompleted ? '#10b981' : isInProgress ? '#3b82f6' : 'var(--text-muted)',
                // Was nowrap: a label wider than its slot overflowed both sides
                // and printed on top of the neighbouring stage's label. The
                // strip already scrolls horizontally, so wrapping inside a
                // fixed slot is what keeps every stage name readable.
                textAlign: 'center', overflowWrap: 'anywhere', width: '100%'
              }}>
                {stage.stage_name}
              </span>
            </div>
            {idx < arr.length - 1 && (
              <div style={{
                height: '2px', flex: 1,
                backgroundColor: isCompleted ? '#10b981' : 'var(--border-color)',
                minWidth: '10px', alignSelf: 'flex-start', marginTop: '9px'
              }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Give a design brief one shape, whatever the server sent.
 *
 * /design-studio/boards/ answers with TailorBriefSerializer -- which has a
 * `design` key -- only for a caller who has a tailor profile and is not the
 * Owner. Everyone else, the Owner included, gets DesignBoardSerializer, whose
 * approved item is under `selected` and which has no `design` at all.
 *
 * The stage panel guarded on `(brief.design || brief.selected)` and then read
 * `brief.design.image_url` on the next line, so for an Owner the guard passed
 * on `selected` and the read threw on `design`. A TypeError inside render hits
 * the error boundary, which unmounts the whole workspace -- and that panel is
 * the only place a stage can be started, paused or completed, so an Owner
 * could not run production on any order that had been through the Design
 * Studio at all.
 *
 * Normalising here rather than at each of the four reads: one place to be
 * wrong, and the next serializer shape that appears has one place to be taught.
 */
const normaliseDesignBrief = (brief) => {
  if (!brief) return null;
  return { ...brief, design: brief.design || brief.selected || null };
};

/**
 * What this garment needs from the store room, shown the moment it is chosen.
 *
 * Reads the boutique's own recipe (the active BOM for the template) so the
 * person taking the order knows BEFORE promising a date whether the racks can
 * stitch it. Read-only and quiet: no recipe, no card.
 */
function MaterialsNeeded({ templateId }) {
  const [bom, setBom] = useState(null);
  useEffect(() => {
    let cancelled = false;
    api.getBoms({ template: templateId })
      .then((data) => {
        const boms = (data.results || data || []).filter((b) => b.is_active);
        if (!cancelled) setBom(boms[0] || null);
      })
      .catch(() => { /* no recipe is a fine answer */ });
    return () => { cancelled = true; };
  }, [templateId]);
  if (!bom || !(bom.lines || []).length) return null;
  return (
    <div style={{ background: 'rgba(0,0,0,0.02)', border: '1px dashed var(--border-color)', borderRadius: '8px', padding: '10px 12px', marginBottom: '16px' }}>
      <div style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-secondary)', marginBottom: '6px' }}>
        Materials this garment needs · {bom.name}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px' }}>
        {bom.lines.map((line) => (
          <span key={line.id} style={{ fontSize: '12.5px', color: 'var(--text-primary)' }}>
            {line.material_name}
            {line.quantity ? ` — ${line.quantity} ${line.unit_display || line.unit || ''}` : (line.quantity_formula ? ' — per measurements' : '')}
            {line.is_optional ? ' (optional)' : ''}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * The Master\'s gathering checklist for one order.
 *
 * Every material the order plans, each with: a tick that records who had it in
 * hand and when, photographs of the actual bolt or spool (camera or gallery)
 * that travel with the order for QC and future rework, and the consumption
 * note once stitching has drawn it. Visibility for everyone; ticking and
 * photographing are the Owner\'s and the Master\'s.
 */
function MaterialsChecklist({ orderId, role, onActivity }) {
  const [plan, setPlan] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [opened, setOpened] = useState(false);
  const [busyLineId, setBusyLineId] = useState(null);
  const canEdit = role === 'Owner' || role === 'Master';

  const refresh = () => api.getMaterialChecklist(orderId)
    .then((data) => { setPlan(data.plan); setLoaded(true); })
    .catch(() => setLoaded(true));
  // Fetch only when someone opens the panel. The registry renders one of
  // these per order card, and an on-mount fetch would fire the whole page's
  // worth of requests at a cross-region API on every visit.
  useEffect(() => { if (opened) refresh(); /* eslint-disable-next-line */ }, [opened, orderId]);

  if (!opened) {
    return (
      <button type="button" className="btn-secondary" style={{ fontSize: '12px', padding: '6px 12px', marginTop: '8px' }} onClick={() => setOpened(true)}>
        Show materials
      </button>
    );
  }
  if (!loaded) return <div style={{ fontSize: '12px', color: 'var(--text-muted)', padding: '6px 0' }}>Loading materials…</div>;
  if (!plan || !(plan.lines || []).length) {
    return <div style={{ fontSize: '12px', color: 'var(--text-muted)', padding: '6px 0' }}>No materials were planned on this order.</div>;
  }
  const remaining = plan.lines.filter((l) => !l.gathered_at).length;

  const act = async (fn) => {
    try { await fn(); await refresh(); if (onActivity) onActivity(); }
    catch (err) { alert(err.message); }
    finally { setBusyLineId(null); }
  };

  return (
    <div style={{ marginTop: '8px' }}>
      <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '8px', color: remaining ? '#b45309' : '#10b981' }}>
        {remaining ? `⚠ ${remaining} of ${plan.lines.length} still to gather` : `✓ All ${plan.lines.length} materials gathered`}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {plan.lines.map((line) => (
          <div key={line.id} style={{ border: '1px solid var(--border-color)', borderRadius: '8px', padding: '8px 10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', cursor: canEdit ? 'pointer' : 'default', flex: '1 1 auto' }}>
                <input
                  type="checkbox"
                  checked={!!line.gathered_at}
                  disabled={!canEdit || busyLineId === line.id}
                  onChange={(e) => {
                    setBusyLineId(line.id);
                    act(() => api.gatherMaterialLine(plan.id, line.id, e.target.checked));
                  }}
                />
                <span style={{ textDecoration: line.gathered_at ? 'line-through' : 'none' }}>
                  {line.material_name} — {line.required_quantity} {line.unit_display || line.unit}
                  {line.is_customer_supplied ? ' (customer\u2019s own)' : ''}
                </span>
              </label>
              {canEdit && (
                <span style={{ display: 'inline-flex', gap: '6px' }}>
                  <label className="btn-secondary" style={{ fontSize: '11px', padding: '3px 8px', cursor: 'pointer' }}>
                    📷
                    <input type="file" accept="image/*" capture="environment" style={{ display: 'none' }}
                      disabled={busyLineId === line.id}
                      onChange={(e) => {
                        const f = e.target.files[0];
                        if (!f) return;
                        setBusyLineId(line.id);
                        act(() => api.addMaterialLinePhoto(plan.id, line.id, f));
                        e.target.value = '';
                      }} />
                  </label>
                  <label className="btn-secondary" style={{ fontSize: '11px', padding: '3px 8px', cursor: 'pointer' }}>
                    🖼
                    <input type="file" accept="image/*" style={{ display: 'none' }}
                      disabled={busyLineId === line.id}
                      onChange={(e) => {
                        const f = e.target.files[0];
                        if (!f) return;
                        setBusyLineId(line.id);
                        act(() => api.addMaterialLinePhoto(plan.id, line.id, f));
                        e.target.value = '';
                      }} />
                  </label>
                </span>
              )}
            </div>
            {(line.gathered_at || Number(line.consumed_quantity) > 0 || (line.photos || []).length > 0) && (
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px', display: 'flex', flexWrap: 'wrap', gap: '4px 12px', alignItems: 'center' }}>
                {line.gathered_at && (
                  <span>Gathered by {line.gathered_by_name || 'staff'} · {new Date(line.gathered_at).toLocaleDateString()}</span>
                )}
                {Number(line.consumed_quantity) > 0 && (
                  <span>{line.consumed_quantity} {line.unit_display || line.unit} used in stitching</span>
                )}
                {(line.photos || []).map((url, i) => (
                  <a key={i} href={url} target="_blank" rel="noreferrer">
                    <img src={url} alt="material" style={{ width: '34px', height: '34px', objectFit: 'cover', borderRadius: '4px', border: '1px solid var(--border-color)' }} />
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * A thin bar across the very top whenever ANY api call is in flight.
 *
 * Every request pays seconds of cross-region latency, and not every control
 * can carry its own spinner -- this is the app-wide answer to "is anything
 * happening?". Driven by window events from services/api.js so the api module
 * stays framework-free.
 */
function NetworkActivityBar() {
  const [active, setActive] = useState(false);
  useEffect(() => {
    const onActivity = (e) => setActive(e.detail > 0);
    window.addEventListener('api-activity', onActivity);
    return () => window.removeEventListener('api-activity', onActivity);
  }, []);
  if (!active) return null;
  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, height: '3px', zIndex: 3000, overflow: 'hidden', background: 'rgba(15, 41, 30, 0.12)' }}>
      <div style={{ position: 'absolute', top: 0, bottom: 0, width: '38%', background: 'var(--text-primary, #0f291e)', borderRadius: '3px', animation: 'apiActivitySweep 1.1s ease-in-out infinite' }} />
    </div>
  );
}

/* ── NAVIGATION ─────────────────────────────────────────────────────────────
   One table, three surfaces: the dashboard sidebar, the order-selector sidebar
   and the phone bottom bar. They were three hand-kept lists and had already
   drifted -- the selector sidebar never gained the Staff entry the dashboard
   sidebar has, and the bottom bar had no Designer branch at all, so a designer
   on a phone was offered "My Assignments", a tab their own sidebar does not
   contain. Read from one place they cannot drift again. */

/* The server module behind each tab, keyed by the dashboardTab VALUE rather
   than by its label -- a renamed tab must not quietly lose its gate.

   `null` means nothing on the server can switch it off: overview, orders,
   customers, assignments, account and settings ride ALWAYS_ON or STRUCTURAL
   prefixes (core/modules.py). Invoices and Analytics are computed in the
   browser out of orders already fetched -- CLIENT_ONLY, no endpoint of their
   own -- so there is no module key to invent for them and they stay visible
   for everyone. */
const NAV_MODULE = {
  overview: null,
  orders: null,
  alterations: null,
  customers: null,
  assignments: null,
  invoices: null,
  analytics: null,
  account: null,
  settings: null,
  designs: 'design_studio',
  designWork: 'design_studio',
  fabrics: 'fabrics',
  inventory: 'inventory',
  staff: 'staff',
  finance: 'finance',
};

/* Hiding a tab is a courtesy; the server is the control and refuses the call
   either way. So a user object carrying no `modules` -- an older token, a
   login cached before the field existed -- sees everything: a workspace that
   blanks its own navigation because one field is absent is worse than one
   offering a tab the server will turn down. */
const hasModule = (user, key) =>
  !key || !Array.isArray(user?.modules) || user.modules.includes(key);

/* `tab in NAV_MODULE`, not a truthy lookup on it. A tab MISSING from the table
   read exactly like one deliberately set to `null`, so a tab added later
   without a NAV_MODULE row was silently visible to every role -- a Tailor
   offered a screen nobody decided to give them, and no way to notice.
   A dev-time warning rather than a second UNGATED set: the table above already
   enumerates the deliberate ones as explicit nulls, and a parallel list is one
   more thing to forget. Still fails open, for the reason in the paragraph
   above -- the point is that the mistake now says so out loud. */
const canSeeTab = (user, tab) => {
  if (import.meta.env.DEV && !(tab in NAV_MODULE)) {
    console.warn(`canSeeTab: no NAV_MODULE row for "${tab}" -- showing it to every role. Add a module key, or an explicit null if that is meant.`);
  }
  return hasModule(user, NAV_MODULE[tab]);
};

/* Grouped by what the owner is DOING, not by the order the screens were built
   in. `phone` marks the few entries the bottom bar carries, `phoneLabel` the
   shorter wording it uses where the sidebar's would wrap. */
const navSectionsFor = (user, t) => {
  const role = user?.role;
  const sections =
    (!role || role === 'Owner') ? [
      { key: 'daily', label: t('nav.groups.daily', 'Daily'), items: [
        { tab: 'overview', icon: Users, label: t('nav.dashboard'), phone: true },
        { tab: 'orders', icon: ShoppingBag, label: t('nav.manageOrders'), phone: true, phoneLabel: t('nav.orders', 'Orders') },
        { tab: 'alterations', icon: Scissors, label: t('nav.alterations', 'Alterations') },
        { tab: 'customers', icon: Users, label: t('nav.customers'), phone: true },
      ] },
      { key: 'design', label: t('nav.groups.design', 'Design'), items: [
        { tab: 'designs', icon: Sparkles, label: t('nav.manageDesigns') },
        { tab: 'designWork', icon: PenTool, label: t('nav.designWork') },
      ] },
      // Fabrics used to sit apart from Inventory in one flat list of eleven,
      // and the roster apart from the employment screen that extends it, so
      // finding anything meant reading all eleven.
      { key: 'stock', label: t('nav.groups.stock', 'Stock'), items: [
        { tab: 'fabrics', icon: Compass, label: t('nav.manageFabrics') },
        { tab: 'inventory', icon: Package, label: t('nav.inventory'), phone: true },
      ] },
      // Manage Tailors is WHO works here; Staff Management is their
      // employment, time and pay. The pairing is the point of the group.
      { key: 'people', label: t('nav.groups.people', 'People'), items: [
        { tab: 'staff', icon: Landmark, label: t('nav.staffManagement') },
      ] },
      { key: 'business', label: t('nav.groups.business', 'Business'), items: [
        { tab: 'finance', icon: Wallet, label: t('nav.finance', 'Cost & P&L') },
        { tab: 'invoices', icon: FileText, label: t('nav.invoices') },
        { tab: 'analytics', icon: BarChart2, label: t('nav.analytics') },
      ] },
    ] : role === 'Master' ? [
      { key: 'master', items: [
        { tab: 'assignments', icon: Scissors, label: t('nav.myAssignments'), phone: true },
        { tab: 'orders', icon: ShoppingBag, label: t('nav.manageOrders'), phone: true, phoneLabel: t('nav.orders', 'Orders') },
        { tab: 'alterations', icon: Scissors, label: t('nav.alterations', 'Alterations') },
        { tab: 'customers', icon: Users, label: t('nav.customers'), phone: true },
        // A Master supervises the floor, so they get the team roster. The
        // screen hides every management control for them and the API strips
        // colleagues' pay from the response -- see StaffSelfOrOwner.
        { tab: 'staff', icon: Landmark, label: t('nav.staffManagement') },
        { tab: 'designWork', icon: PenTool, label: t('nav.designWork') },
      ] },
    ] : role === 'Designer' ? [
      { key: 'designer', items: [
        { tab: 'designWork', icon: PenTool, label: t('nav.myWork'), phone: true },
        { tab: 'designs', icon: Sparkles, label: t('nav.designStudio') },
      ] },
    ] : [
      { key: 'production', items: [
        { tab: 'assignments', icon: Scissors, label: t('nav.myAssignments'), phone: true },
        // Production staff record their own hours here. Labelled for what it
        // is to them -- the screen opens on Attendance and shows only their
        // own record. Without this entry a tailor cannot check in at all.
        { tab: 'staff', icon: Clock, label: t('nav.myAttendance') },
      ] },
    ];

  // A rule rather than a heading: these are the way OUT of the workspace, not
  // another room in it. Shared by every role, so a tailor with two entries
  // gets the same separation as the owner with eleven. Account takes a slot on
  // the bottom bar only for the roles whose own section cannot fill it.
  const roomy = !role || role === 'Owner' || role === 'Master';
  return [...sections, { key: 'session', divider: true, items: [
    { tab: 'account', icon: User, label: t('nav.account'), phone: !roomy },
    { tab: 'settings', icon: Settings, label: t('nav.settings') },
  ] }];
};

/* Drop what this user cannot reach, then drop any group left with nothing
   under it -- otherwise the sidebar grows headings over empty space. */
const visibleNav = (user, t) => navSectionsFor(user, t)
  .map((section) => ({ ...section, items: section.items.filter((i) => canSeeTab(user, i.tab)) }))
  .filter((section) => section.items.length);

/** The sidebar list. `onPick` differs by view: the order selector has to leave
    itself for the dashboard before a tab means anything. */
/** One entry in the sidebar. Collapsed, it is the icon alone and the label
 *  follows the pointer as a flyout -- position: fixed, because both the
 *  sidebar and the scrolling nav clip anything that pokes out of them. */
function NavItem({ icon: Icon, label, active, onClick, collapsed }) {
  const [flyout, setFlyout] = useState(null);
  const show = (e) => {
    if (!collapsed) return;
    const r = e.currentTarget.getBoundingClientRect();
    setFlyout({ top: r.top + r.height / 2, left: r.right + 10 });
  };
  const hide = () => setFlyout(null);
  return (
    <a
      className={`portal-menu-item${active ? ' active' : ''}`}
      role="button"
      tabIndex={0}
      aria-label={collapsed ? label : undefined}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } }}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <Icon size={16} />
      <span className="portal-menu-label">{label}</span>
      {collapsed && flyout && (
        <span className="portal-flyout" role="tooltip" style={{ top: flyout.top, left: flyout.left }}>{label}</span>
      )}
    </a>
  );
}

function PortalMenu({ sections, activeTab, onPick, collapsed = false }) {
  return sections.map((section) => (
    <React.Fragment key={section.key}>
      {section.divider && <div className="portal-menu-divider" />}
      {section.label && <div className="portal-menu-group">{section.label}</div>}
      {section.items.map(({ tab, icon, label }) => (
        <NavItem key={tab} icon={icon} label={label} active={activeTab === tab}
                 collapsed={collapsed} onClick={() => onPick(tab)} />
      ))}
    </React.Fragment>
  ));
}


function App() {
  // The marketing site is static HTML at / and no longer a view in here -- see
  // frontend/index.html. This bundle is the workspace, served from /app, so it
  // opens on the sign-in screen and "back" links leave for the marketing site.
  // 'login', 'signup', 'forgot', 'reset', 'dashboard', 'order-selector', 'wizard', 'confirmed'
  //
  // Opens on 'reset' when the address bar carries a reset token, and that wins
  // over a restored session on purpose: whoever followed the link may still be
  // signed in here -- the ordinary case when an owner has merely forgotten a
  // password rather than lost it -- and sending them to the dashboard would
  // swallow the link without ever showing the form.
  const [view, setView] = useState(
    () => new URLSearchParams(window.location.search).get('reset') ? 'reset' : 'login');
  const [requestedTab, setDashboardTab] = useState('overview'); // 'overview', 'fabrics', 'tailors', 'designs' -- resolved into dashboardTab below
  // Sidebar width is the reader's choice, remembered per device. Desktop
  // only: below 1024px the sidebar is the drawer and always shows labels.
  const [navCollapsed, setNavCollapsed] = useState(() => {
    try { return localStorage.getItem('nav_collapsed') === '1'; } catch { return false; }
  });
  const toggleNav = () => setNavCollapsed((c) => {
    try { localStorage.setItem('nav_collapsed', c ? '0' : '1'); } catch { /* per-device convenience only */ }
    return !c;
  });
  const [currentUser, setCurrentUser] = useState(null);
  const { t, language } = useLanguage();
  const currentUserName = currentUser?.first_name || currentUser?.name || currentUser?.email?.split('@')[0] || 'User';

  // Every navigation surface reads this one list -- see NAV_MODULE above.
  const navSections = visibleNav(currentUser, t);

  // The tab actually shown, which is not always the tab that was asked for.
  // The opening tab is picked from the role alone (checkAuthSession,
  // handleLoginSubmit) and a restored session is where that goes stale: the
  // owner may have closed that module for the role since, leaving a screen
  // that 403s on every call it makes. Hiding the sidebar entry does not help
  // on its own -- nothing stops a stale requestedTab from still pointing at
  // it -- so resolve it here, where a hidden tab simply never renders.
  const navTabs = navSections.flatMap((s) => s.items.map((i) => i.tab));
  const dashboardTab = (!navTabs.length || navTabs.includes(requestedTab)) ? requestedTab : navTabs[0];

  
  // Login Form State
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);

  // Password reset. `resetToken` is read out of the query string on mount --
  // the link in the email is the only way into the 'reset' view, and the
  // browser following it has no session and no tenant header yet, so the token
  // carries the schema itself (see PasswordResetRequestView).
  const [resetEmail, setResetEmail] = useState('');
  const [resetSent, setResetSent] = useState(false);
  // Read once, as the initial value, rather than in an effect: setting state
  // synchronously inside an effect makes React render the login screen first
  // and the reset screen a frame later, which is a visible flash of the wrong
  // page on the one screen where the user has just clicked a link in an email.
  const [resetToken, setResetToken] = useState(
    () => new URLSearchParams(window.location.search).get('reset'));
  const [resetPassword, setResetPassword] = useState('');
  const [resetConfirm, setResetConfirm] = useState('');
  const [resetDone, setResetDone] = useState(false);
  // Shown inside the auth card. These screens deliberately do not use the
  // alert() the rest of this file reaches for: a modal dialog on top of a
  // sign-in form is the wrong shape for "that address is not valid".
  const [authError, setAuthError] = useState(null);
  const [authBusy, setAuthBusy] = useState(false);
  // Logout asks first: one mis-tap on a phone menu ended the whole session,
  // and the POST behind it takes seconds with nothing on screen saying so.
  // Getting-started checklist: dismissed per device+boutique, and it also
  // disappears on its own once every step is genuinely done.
  const [onboardingDismissed, setOnboardingDismissed] = useState(() => {
    try {
      return localStorage.getItem(`onboarding_dismissed_${localStorage.getItem('tenant_id') || ''}`) === '1';
    } catch { return false; }
  });
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [logoutBusy, setLogoutBusy] = useState(false);

  // Signup Wizard State
  const [signupStep, setSignupStep] = useState(1); // 1: Account, 2: Verify, 3: Profile, 4: Prefs, 5: Complete

  const [signupForm, setSignupForm] = useState({
    first_name: '',
    last_name: '',
    email_address: '',
    mobile_number: '',
    password: ''
  });
  const [signupBusy, setSignupBusy] = useState(false);
  const [signupError, setSignupError] = useState(null);
  const [boutiqueName, setBoutiqueName] = useState('');
  const [boutiqueAddress, setBoutiqueAddress] = useState('');

  // Customer/Order Wizard State
  const [currentStep, setCurrentStep] = useState(1);
  // Which garment tile is fetching its template right now: the load takes
  // seconds against the remote database, and a silent tile invites re-clicks.
  const [addingGarmentKey, setAddingGarmentKey] = useState(null);

  // A wizard step lands read from the top, not wherever the previous step's
  // Next button happened to leave the scroll.
  useEffect(() => {
    // Instant, not smooth: the new step's content is still mounting, and a
    // smooth scroll gets cancelled by the layout shifting under it.
    window.scrollTo(0, 0);
  }, [view, currentStep, signupStep]);

  const [customerId, setCustomerId] = useState(null);
  const [customerForm, setCustomerForm] = useState(DEFAULT_CUSTOMER_DATA);
  const [profilePhoto, setProfilePhoto] = useState(null);
  const [profilePhotoPreview, setProfilePhotoPreview] = useState(null);
  
  // Garment templates. `garmentTemplates` is the summary list that fills the
  // picker; `garmentJobs` is the dresses on this order, each holding the full
  // template it renders from and the answers given so far. One order can carry a
  // lehenga, its blouse and a dupatta, so this is a list, not a single value.
  const [garmentTemplates, setGarmentTemplates] = useState([]);
  const [garmentJobs, setGarmentJobs] = useState([]);
  const [activePairingGarment, setActivePairingGarment] = useState(null);
  // The order being written lives on the server as an OrderDraft; this is a
  // cache of it. Refreshing, following the step-4 empty-state button, or
  // opening a second tab must not be able to destroy work already done --
  // which is exactly what happened while the wizard's only copy was here.
  const [draftId, setDraftId] = useState(null);
  const [draftVersion, setDraftVersion] = useState(null);
  // idle | saving | saved | failed | conflict
  const [draftSaveState, setDraftSaveState] = useState('idle');
  const [resumableDrafts, setResumableDrafts] = useState([]);
  // Which draft is asking to be confirmed for discard. An in-app step
  // rather than window.confirm: a destructive action should not depend on
  // a browser dialog, which can be suppressed by the browser, by an
  // extension, or by the automation that is supposed to be testing it --
  // and a control nobody can test is a control nobody should trust.
  const [discardingDraftId, setDiscardingDraftId] = useState(null);
  const [garmentQuantityErrors, setGarmentQuantityErrors] = useState({});
  const [garmentErrors, setGarmentErrors] = useState({});
  const [garmentTemplatesError, setGarmentTemplatesError] = useState(null);
  // Bumped after any design write so the library refetches its counts and grid.
  const [designLibraryToken, setDesignLibraryToken] = useState(0);
  const [designsView, setDesignsView] = useState('dashboard'); // 'dashboard' | 'library'
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // Wizard Details State
  const [designNotes, setDesignNotes] = useState('');
  const [designFiles, setDesignFiles] = useState([]);
  const [designPreviews, setDesignPreviews] = useState([]);
  const [designSourceTab, setDesignSourceTab] = useState('studio'); // 'studio', 'references'
  // Board id and selection handed up by the Design Studio, attached to the
  // order once it is created in step 6.
  const [designBoard, setDesignBoard] = useState({ boardId: null, selected: null, approved: false });
  const [selectedDesignTemplates, setSelectedDesignTemplates] = useState([]);
  const [designSource, setDesignSource] = useState('BOUTIQUE_CATALOG');
  const [designLinks, setDesignLinks] = useState('');
  const [fabricTab, setFabricTab] = useState('boutique'); // 'my-fabric', 'boutique', 'accessories'
  const [accessorySubTab, setAccessorySubTab] = useState('boutique'); // 'boutique', 'customer'
  const [paymentPhase, setPaymentPhase] = useState(false);
  // Step 2 has two phases the way step 6 does: choosing fabrics and
  // accessories, then reading back everything chosen for every dress before
  // moving on to the customer's details. A phase rather than a step number,
  // because the number is what drafts save and resume by.
  const [selectionReviewPhase, setSelectionReviewPhase] = useState(false);
  const [paymentOption, setPaymentOption] = useState('full'); // 'full' or 'partial'
  const [deliveryMethod, setDeliveryMethod] = useState('Direct Pickup');
  const [courierService, setCourierService] = useState('');
  const [trackingNumber, setTrackingNumber] = useState('');
  const [deliveryAddress, setDeliveryAddress] = useState('');
  const [advancePaymentAmount, setAdvancePaymentAmount] = useState(0);
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [specialInstructions, setSpecialInstructions] = useState('');

  const [fabricFiles, setFabricFiles] = useState([]);
  const [fabricPreviews, setFabricPreviews] = useState([]);
  const [selectedFabric, setSelectedFabric] = useState(null);
  const [selectedTailor, setSelectedTailor] = useState(null);
  const [selectedMaster, setSelectedMaster] = useState(null);
  // Order-level money only. Everything garment-shaped -- base, fabric,
  // embroidery, customization, tailoring -- lives on each entry in
  // garmentJobs.pricing now, because one flat set is exactly how a Blouse +
  // Lehenga order came to be priced as whichever garment the profile named.
  const [quotePrices, setQuotePrices] = useState({ packaging: 500, discount: 0 });
  const [showInvoiceModal, setShowInvoiceModal] = useState(false);

  // Fabrics CRUD State
  const [showFabricModal, setShowFabricModal] = useState(false);
  const [editingFabric, setEditingFabric] = useState(null);
  // Library filters: one predicate over the fabrics already loaded.
  const [fabricQuery, setFabricQuery] = useState({ search: '', material: 'All', colour: 'All', availability: 'All', sort: 'newest' });
  const [fabricSaving, setFabricSaving] = useState(false);
  const [fabricGroups, setFabricGroups] = useState([blankGroup()]);
  const fabricTaxonomy = useFabricTaxonomy();
  const [fabricUploads, setFabricUploads] = useState(0);
  const fabricCount = fabricGroups.reduce((n, g) => n + g.materials.length, 0);

  // Tailors CRUD State
  // Recording a payment: which row is in flight, and what went wrong. Shown in
  // the Invoices header rather than through alert() -- a modal dialog over a
  // ledger the owner is reading down is the wrong shape for "that did not save".
  const [wizardError, setWizardError] = useState(null);
  const [savingPaymentId, setSavingPaymentId] = useState(null);
  const [paymentError, setPaymentError] = useState(null);

  // Designs CRUD State
  const [showDesignModal, setShowDesignModal] = useState(false);
  const [editingDesign, setEditingDesign] = useState(null);
  const [designSaving, setDesignSaving] = useState(false);
  const [designForm, setDesignForm] = useState({
    name: '',
    garment_type: 'Lehenga',
    neckline_style: '',
    sleeve_style: '',
    image_url: '',
    is_boutique: true,
    price: 0,
    description: ''
  });

  // The old effect that synced a single base/fabric price from
  // customerForm.garment_type is gone: money is seeded per garment in
  // addGarment and edited per garment on the review step. A boutique fabric's
  // suggested charge is applied to a garment when the owner types it, not
  // guessed at three metres against whichever dress came first.

  // The garment list drives the whole order form, and comes from the catalogue
  // rather than a hardcoded array.
  //
  // Loaded per signed-in user, not on mount. The endpoint needs a token, and
  // on mount there is none -- the app opens on the landing page and the user
  // logs in afterwards. Fetching once on mount meant the request 401'd, the
  // list stayed empty, and the order form offered no garments at all.
  const loadGarmentTemplates = useCallback(async () => {
    if (!localStorage.getItem('token')) return;
    setGarmentTemplatesError(null);
    try {
      const data = await api.getGarmentTemplates();
      setGarmentTemplates(data.results || data);
    } catch (err) {
      console.error('Could not load garment templates', err);
      setGarmentTemplates([]);
      setGarmentTemplatesError(err.message || 'Could not load the garment list.');
    }
  }, []);

  useEffect(() => {
    loadGarmentTemplates();
  }, [currentUser, loadGarmentTemplates]);

  const addGarment = async (key, skipPairingPrompt = false) => {
    if (garmentJobs.some(job => job.key === key)) return;
    if (addingGarmentKey) return;
    setAddingGarmentKey(key);
    try {
      const template = await api.getGarmentTemplate(key);
      setGarmentJobs(prev => [...prev, {
        key, template, values: {}, quantities: {}, sources: {}, brought: {},
        pricing: { base: GARMENT_PRICES[template.name] || 15000, fabric: 0,
                   embroidery: 0, customization: 0, tailoring: 0 },
      }]);
      if (!skipPairingPrompt) {
        const pairConfig = getGarmentPairConfig(key, template.name);
        if (pairConfig) {
          setActivePairingGarment({ key, name: template.name });
        }
      }
    } catch (err) {
      console.error(err);
      alert('Could not load that garment form.');
    } finally {
      setAddingGarmentKey(null);
    }
  };

  const handleAddPairedGarments = async (pairKeys) => {
    for (const pairKey of pairKeys) {
      await addGarment(pairKey, true);
    }
  };

  const handleSaveReferenceImage = (garmentKey, imageDataUrl) => {
    setGarmentJobs(prev => prev.map(job => (
      job.key === garmentKey ? { ...job, referenceImage: imageDataUrl } : job
    )));
  };



  // Pricing, the dashboard and the stage tracker still read the single
  // garment_type on the customer, so it follows the first dress on the order
  // until those move over to the job list.
  //
  // Derived rather than assigned inside addGarment: that read garmentJobs from
  // the closure, so two garments added in the same tick both saw an empty list
  // and the second overwrote the first -- the cost sidebar then named the wrong
  // garment. Deriving also keeps it right when the first dress is removed.
  useEffect(() => {
    const first = garmentJobs[0]?.template?.name;
    if (first) {
      setCustomerForm(prev => (prev.garment_type === first ? prev : { ...prev, garment_type: first }));
    }
  }, [garmentJobs]);

  const removeGarment = (key) => {
    setGarmentJobs(prev => prev.filter(job => job.key !== key));
    setGarmentErrors(prev => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const updateGarmentValues = (key, values) => {
    setGarmentJobs(prev => prev.map(job => (job.key === key ? { ...job, values } : job)));
  };

  /** How much of a chosen material this dress needs, keyed by template field. */
  const updateGarmentQuantity = (key, fieldKey, quantity) => {
    setGarmentJobs(prev => prev.map(job => (
      job.key === key
        ? { ...job, quantities: { ...(job.quantities || {}), [fieldKey]: quantity } }
        : job
    )));
  };

  /** Where one material comes from: boutique stock, or the customer's own. */
  const updateGarmentSource = (key, fieldKey, source) => {
    setGarmentJobs(prev => prev.map(job => (
      job.key === key
        ? { ...job, sources: { ...(job.sources || {}), [fieldKey]: source } }
        : job
    )));
  };

  /** What the customer brought for one material -- its name and its unit. */
  const updateGarmentBrought = (key, fieldKey, entry) => {
    setGarmentJobs(prev => prev.map(job => (
      job.key === key
        ? { ...job, brought: { ...(job.brought || {}), [fieldKey]: entry } }
        : job
    )));
  };

  /** What the order's Material Source answer means for a line nobody has
   *  spoken for yet. "Mixed" deliberately defaults to stock and waits to be
   *  told, because mixed means the answer differs line by line. */
  const defaultMaterialSource = (job) =>
    (job.values?.material_source === 'customer' ? 'CUSTOMER' : 'STORE');

  /** The material fields on a template, with the item chosen for each.
   *
   *  Read off the template rather than off a hardcoded list, so a garment that
   *  gains a material field gains a material line with it. */
  const garmentMaterialFields = (job) => {
    const fallback = defaultMaterialSource(job);
    return (job.template?.sections || [])
      .flatMap(section => section.fields || [])
      .filter(field => field.field_type === 'inventory_ref')
      .map(field => {
        const source = job.sources?.[field.key] || fallback;
        const brought = job.brought?.[field.key] || {};
        return {
          field,
          source,
          itemId: job.values?.[field.key],
          name: (brought.name || '').trim(),
          unit: brought.unit,
        };
      })
      // A line counts once it names something: a roll off the rack, or the
      // cloth the customer handed over. Nothing named, nothing to plan.
      .filter(entry => (entry.source === 'CUSTOMER' ? entry.name : entry.itemId));
  };

  /** One material line, in the shape the API stores.
   *
   *  Customer material carries its own name and never an inventory item -- the
   *  serializer rejects the combination, because their cloth is not stock and
   *  must never be reserved or deducted from it.
   */
  const materialLine = (job) => ({ field, source, itemId, name, unit }) => (
    source === 'CUSTOMER'
      ? {
        field_key: field.key,
        free_text: name,
        quantity: job.quantities?.[field.key],
        unit,
        source: 'CUSTOMER',
      }
      : {
        field_key: field.key,
        inventory_item: itemId,
        quantity: job.quantities?.[field.key],
        source: 'STORE',
      }
  );

  /** Validate every dress on the order; returns true when all of them pass. */
  const validateGarments = ({ partial = false } = {}) => {
    const errors = {};
    const quantityErrors = {};
    garmentJobs.forEach(job => {
      const jobErrors = validateSpec(job.template, job.values, { partial });
      if (Object.keys(jobErrors).length) errors[job.key] = jobErrors;

      // A material chosen with no quantity cannot be reserved or consumed, so
      // it would reach production as a name with no effect on stock. Ask for
      // the number now rather than defaulting to one nobody decided. Skipped
      // while saving a draft, which is expected to be half-filled.
      if (partial) return;
      const jobQuantityErrors = {};
      garmentMaterialFields(job).forEach(({ field }) => {
        const raw = job.quantities?.[field.key];
        const quantity = Number(raw);
        if (raw === undefined || raw === '' || Number.isNaN(quantity) || quantity <= 0) {
          jobQuantityErrors[field.key] = 'Enter how much of this material this garment needs.';
        }
      });
      // A quantity typed against a customer material nobody named would be
      // dropped on the way out, silently. Say so instead.
      const fallbackSource = defaultMaterialSource(job);
      (job.template?.sections || [])
        .flatMap(section => section.fields || [])
        .filter(field => field.field_type === 'inventory_ref')
        .forEach(field => {
          const source = job.sources?.[field.key] || fallbackSource;
          const name = (job.brought?.[field.key]?.name || '').trim();
          const raw = job.quantities?.[field.key];
          if (source === 'CUSTOMER' && !name && raw !== undefined && raw !== '') {
            jobQuantityErrors[field.key] = 'Name what the customer brought for this.';
          }
        });
      if (Object.keys(jobQuantityErrors).length) quantityErrors[job.key] = jobQuantityErrors;
    });
    setGarmentErrors(errors);
    setGarmentQuantityErrors(quantityErrors);
    return Object.keys(errors).length === 0 && Object.keys(quantityErrors).length === 0;
  };

  /** Every dress on the order being written, as one line.
   *
   *  The wizard's counterpart to orderGarmentLabel, which answers the same
   *  question for an order that already exists. Derived from garmentJobs --
   *  the actual garments chosen -- and never from customerForm.garment_type,
   *  which holds one value and follows whichever dress was picked first.
   *
   *  A single definition because the expression had already been copied to two
   *  sidebars and a third read the customer field instead: the step-5 summary
   *  showed "Women - Blouse" for a blouse-and-lehenga order, on the screen
   *  where the owner assigns staff and reads the price. Copies drift; this is
   *  the fix for the drift as well as for the symptom.
   */
  const wizardGarmentLabel = garmentJobs.length
    ? garmentJobs.map(job => job.template?.name).filter(Boolean).join(', ')
    : (customerForm.garment_type || '');

  /** Everything the wizard is holding, in a shape the draft can store.
   *
   *  Garment templates are stored by key rather than as the whole fetched
   *  object: the template is boutique configuration that can be re-read, and
   *  storing a copy of it would mean resuming a draft against a stale one.
   */
  const serialiseWizard = () => ({
    ...customerForm,
    measurements: customerForm.measurements || {},
    garments: garmentJobs.map(job => ({
      key: job.key,
      template: job.template?.id,
      template_key: job.template?.key || job.key,
      spec: splitSpec(job.template, job.values).spec,
      measurements: splitSpec(job.template, job.values).measurements,
      values: job.values,
      quantities: job.quantities || {},
      pricing: job.pricing || {},
      design: job.design || {},
      fabrics: job.fabrics || {},
      sources: job.sources || {},
      brought: job.brought || {},
      materials: garmentMaterialFields(job).map(materialLine(job)),
    })),
    design: {
      notes: designNotes, links: designLinks, source: designSource,
      templates: selectedDesignTemplates,
    },
    fabric: {
      tab: fabricTab,
      selected_id: selectedFabric?.id || null,
      selected_name: selectedFabric?.name || null,
    },
    staff: { tailor_id: selectedTailor?.id || null, master_id: selectedMaster?.id || null },
    prices: quotePrices,
    delivery: { method: deliveryMethod, courier: courierService,
                tracking: trackingNumber, address: deliveryAddress },
    payment: { option: paymentOption, advance: advancePaymentAmount },
    special_instructions: specialInstructions,
  });

  /** Put a saved draft back on screen, exactly where it was left. */
  const hydrateWizard = async (draft) => {
    const payload = draft.payload || {};
    setDraftId(draft.id);
    setDraftVersion(draft.version);
    setCustomerId(draft.customer || null);

    const { garments = [], design = {}, fabric = {}, staff = {}, prices,
            delivery = {}, payment = {}, ...customer } = payload;
    setCustomerForm(prev => ({ ...prev, ...customer }));

    // Templates are re-fetched rather than restored from the draft, so a
    // resumed order is always built against the boutique's current garment
    // definitions.
    const rebuilt = [];
    for (const garment of garments) {
      try {
        const template = await api.getGarmentTemplate(garment.template_key);
        rebuilt.push({
          key: garment.key || garment.template_key,
          template,
          values: garment.values || {},
          quantities: garment.quantities || {},
          sources: garment.sources || {},
          brought: garment.brought || {},
          pricing: garment.pricing || {},
          design: garment.design || {},
          fabrics: garment.fabrics || {},
        });
      } catch (err) {
        console.error('Could not reload the garment template', garment.template_key, err);
      }
    }
    // A draft written before pricing moved per-garment holds one flat price
    // set. Put it on the first garment -- which is exactly what the flat model
    // meant by it -- so the owner sees the same money and the next save writes
    // the draft forward in the new shape.
    const hasJobPricing = rebuilt.some(job =>
      Object.values(job.pricing || {}).some(v => parseFloat(v || 0)));
    if (!hasJobPricing && rebuilt.length && prices) {
      rebuilt[0] = { ...rebuilt[0], pricing: {
        base: prices.base || 0, fabric: prices.fabric || 0,
        embroidery: prices.embroidery || 0,
        customization: prices.customization || 0,
        tailoring: prices.tailoring || 0,
      } };
    }
    setGarmentJobs(rebuilt);

    setDesignNotes(design.notes || '');
    setDesignLinks(design.links || '');
    if (design.source) setDesignSource(design.source);
    setSelectedDesignTemplates(design.templates || []);
    if (fabric.tab) setFabricTab(fabric.tab);
    if (prices) setQuotePrices({ packaging: prices.packaging ?? 500,
                                 discount: prices.discount ?? 0 });
    if (delivery.method) setDeliveryMethod(delivery.method);
    if (payment.option) setPaymentOption(payment.option);
    if (payment.advance !== undefined) setAdvancePaymentAmount(payment.advance);
    setSpecialInstructions(payload.special_instructions || '');
    setSelectionReviewPhase(false);
    setCurrentStep(draft.current_step || 1);
    setView('wizard');
  };

  /** Write the wizard to its draft, creating one on first save.
   *
   *  Returns the draft id, so callers that are about to navigate away can be
   *  sure the work is on the server before they go.
   */
  const persistDraft = async ({ step } = {}) => {
    const payload = serialiseWizard();
    const current_step = step || currentStep;
    setDraftSaveState('saving');
    try {
      if (!draftId) {
        const created = await api.createOrderDraft({
          payload, current_step, customer: customerId || null,
        });
        setDraftId(created.id);
        setDraftVersion(created.version);
        setDraftSaveState('saved');
        return created.id;
      }
      const saved = await api.updateOrderDraft(draftId, {
        payload, current_step, customer: customerId || null, version: draftVersion,
      });
      setDraftVersion(saved.version);
      setDraftSaveState('saved');
      return saved.id;
    } catch (err) {
      // A conflict is not a failure to save -- it is this tab holding an older
      // copy than the server. Overwriting would throw away whatever the other
      // tab did, so the tab is marked stale and the person is told to reload.
      setDraftSaveState(err.isConflict ? 'conflict' : 'failed');
      if (!err.isConflict) console.error('Could not save the draft', err);
      throw err;
    }
  };

  // Active Selected Dashboard Order for progress tracker
  const [selectedDashboardOrder, setSelectedDashboardOrder] = useState(null);
  const [updatingOrderStatusId, setUpdatingOrderStatusId] = useState(null);
  const [expandedDna, setExpandedDna] = useState({});
  const [selectedDirectoryCustomer, setSelectedDirectoryCustomer] = useState(null);
  // Which alteration the Alterations tab should open on. Set when somebody
  // follows one from an order card or a customer's file, cleared once the tab
  // has been entered so going back to the tab shows the register again.
  const [openAlterationId, setOpenAlterationId] = useState(null);
  const openAlteration = (id) => {
    setOpenAlterationId(id);
    setSelectedDirectoryCustomer(null);
    setDashboardTab('alterations');
  };
  const [directoryDetailLoading, setDirectoryDetailLoading] = useState(false);
  // Which order in the customer profile is expanded to show its production
  // progress. Opening a client's order used to throw them into the new-order
  // wizard, so there was no way to answer "where is my dress?" from the profile.
  const [expandedCustomerOrderId, setExpandedCustomerOrderId] = useState(null);
  const [approvingDesignId, setApprovingDesignId] = useState(null);
  const [submittingCompletionId, setSubmittingCompletionId] = useState(null);
  const [assigningStageKey, setAssigningStageKey] = useState(null);

  // Backend fetched collections
  const [dashboardData, setDashboardData] = useState(null);
  const [tailors, setTailors] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [showAppointmentModal, setShowAppointmentModal] = useState(false);
  const [appointmentForm, setAppointmentForm] = useState({
    customer: '', appointment_type: 'TRIAL', scheduled_time: '', assigned_staff: '', notes: '',
  });
  const [savingAppointment, setSavingAppointment] = useState(false);
  // The appointment the modal is looking at. Null means the modal is booking a
  // new one -- same form either way, because it is the same five fields.
  const [editingAppointment, setEditingAppointment] = useState(null);
  // Cancelled and past appointments are the record, and the owner has to be
  // able to open one. Off by default: the panel is about the day ahead.
  const [showAllAppointments, setShowAllAppointments] = useState(false);
  const [fabrics, setFabrics] = useState([]);
  const [allDesigns, setAllDesigns] = useState([]);
  const [customersList, setCustomersList] = useState([]);
  const [ordersList, setOrdersList] = useState([]);
  // Customer messages still waiting for the owner to send them, for every
  // order at once. Refreshed with the dashboard, so advancing an order's
  // status makes its new message appear without a reload.
  const [queuedMessages, setQueuedMessages] = useState([]);
  const [confirmedOrder, setConfirmedOrder] = useState(null);

  // Existing Customer Search Modal
  const [showSearchModal, setShowSearchModal] = useState(false);
  const [searchModalQuery, setSearchModalQuery] = useState('');
  const [allCustomers, setAllCustomers] = useState([]);

  // Search & Filters for dashboard
  const [searchQuery, setSearchQuery] = useState('');
  const [customerTypeFilter, setCustomerTypeFilter] = useState('All');
  const [ordersSearch, setOrdersSearch] = useState('');
  const [ordersFilterTab, setOrdersFilterTab] = useState('All');
  const [ordersView, setOrdersView] = useState('kanban');

  // One predicate for the order registry, whichever way it is drawn: the list
  // and the board show the same orders under the same filter and search.
  const orderMatchesFilters = (order) => {
    if (ordersFilterTab === 'Active') {
      if (['Shipped', 'Delivered'].includes(order.order_status)) return false;
    } else if (ordersFilterTab === 'Shipped') {
      if (order.order_status !== 'Shipped') return false;
    } else if (ordersFilterTab === 'Delivered') {
      if (order.order_status !== 'Delivered') return false;
    }
    if (ordersSearch.trim()) {
      const query = ordersSearch.toLowerCase();
      const matchesId = order.order_id.toLowerCase().includes(query)
        || orderRef(order).toLowerCase().includes(query);
      const matchesClient = (order.customer_name || '').toLowerCase().includes(query);
      return matchesId || matchesClient;
    }
    return true;
  };
  const [invoiceSearch, setInvoiceSearch] = useState('');
  const [invoiceFilter, setInvoiceFilter] = useState('All');
  const [loading, setLoading] = useState(true);
  const [whatsappStatus, setWhatsappStatus] = useState({ connected: false, status: 'disconnected', qrCode: null });
  const [boutiqueSettings, setBoutiqueSettings] = useState(null);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [logoFile, setLogoFile] = useState(null);
  const [drapingLoading, setDrapingLoading] = useState(false);
  const [drapingCompleted, setDrapingCompleted] = useState(false);
  const [drapedImage, setDrapedImage] = useState('');
  const [showDrapingModal, setShowDrapingModal] = useState(false);
  
  const [activeReviewStage, setActiveReviewStage] = useState(null);
  const [activeReviewOrder, setActiveReviewOrder] = useState(null);
  const [stageReviewComments, setStageReviewComments] = useState('');
  const [stageReviewImage, setStageReviewImage] = useState(null);
  const [selectedStageObj, setSelectedStageObj] = useState(null);
  const [stageDesignBrief, setStageDesignBrief] = useState(null);
  const [productionNotesDraft, setProductionNotesDraft] = useState('');
  const [savingProductionNotes, setSavingProductionNotes] = useState(false);
  const [selectedPerformerId, setSelectedPerformerId] = useState('');
  const [stageTransitionBusy, setStageTransitionBusy] = useState(false);
  // The two sanctioned reversals, both behind a mandatory-reason dialog:
  // {type: 'reopen'|'failqc'} while the dialog is open.
  const [reversalPrompt, setReversalPrompt] = useState(null);
  const [reversalReason, setReversalReason] = useState('');
  const [reversalBusy, setReversalBusy] = useState(false);
  const [globalError, setGlobalError] = useState(null);
  // Names of the dashboard collections that failed to load, so the UI can say so
  // instead of rendering an empty directory as if the boutique had no clients.
  const [loadErrors, setLoadErrors] = useState([]);

  useEffect(() => {
    const handleErr = (event) => {
      setGlobalError(event.error ? event.error.stack || event.error.message : event.message);
    };
    const handleRejection = (event) => {
      const reason = event.reason;
      setGlobalError(reason ? reason.stack || reason.message || String(reason) : 'Unhandled promise rejection');
    };
    window.addEventListener('error', handleErr);
    window.addEventListener('unhandledrejection', handleRejection);
    return () => {
      window.removeEventListener('error', handleErr);
      window.removeEventListener('unhandledrejection', handleRejection);
    };
  }, []);

  const [notifications, setNotifications] = useState([]);
  const [showNotificationsDrawer, setShowNotificationsDrawer] = useState(false);
  // In-flight guards, same shape as signupBusy/savingPaymentId: a boolean for
  // the shared bell, an order/row id for per-row controls.
  const [markingNotificationsRead, setMarkingNotificationsRead] = useState(false);
  const [updatingStatusOrderId, setUpdatingStatusOrderId] = useState(null);
  const [savingVerificationOrderId, setSavingVerificationOrderId] = useState(null);
  const [assigningWorkflowOrderId, setAssigningWorkflowOrderId] = useState(null);
  const [deletingFabricId, setDeletingFabricId] = useState(null);
  const [deletingDraftId, setDeletingDraftId] = useState(null);

  // `user` is passed explicitly by callers that have just signed in: setCurrentUser
  // has not committed yet at that point, so reading it from state would bail out
  // and leave the bell empty until some later refresh.
  const fetchNotifications = async (user = currentUser) => {
    if (!user) return;
    const data = await api.getNotifications(user.role || 'Owner', user.email);
    setNotifications(data);
  };

  // Persisted Session check.
  //
  // The reset link is checked first and wins. Someone following it may well
  // still hold a live token in this browser -- that is the ordinary case when
  // an owner resets a password they simply forgot rather than one that was
  // stolen -- and restoring them to the dashboard would swallow the link
  // without ever showing the form.
  useEffect(() => {
    if (resetToken) {
      // Take it out of the address bar so the token is not left in history,
      // in a bookmark, or in whatever the next Referer header carries.
      window.history.replaceState({}, '', window.location.pathname);
      // checkAuthSession is what normally clears `loading`, and it is
      // deliberately skipped on this path. Without this line the flag stays
      // true forever, and the moment the reset finishes and the view goes back
      // to 'login' the app renders its full-screen "Loading Atelier CRM..."
      // spinner instead of the sign-in form -- with nothing left to load and
      // no way out but a reload.
      setLoading(false);
      return;
    }
    checkAuthSession();
  }, []);

  const handleForgotSubmit = async (e) => {
    if (e) e.preventDefault();
    const email = resetEmail.trim();
    if (!email) {
      setAuthError('Enter the email address you sign in with.');
      return;
    }
    setAuthBusy(true);
    setAuthError(null);
    try {
      await api.requestPasswordReset(email);
      // Shown whatever the server found. It answers identically for an address
      // it knows and one it does not -- on purpose -- so telling the two apart
      // here would undo that.
      setResetSent(true);
    } catch (err) {
      setAuthError(err.message || 'Could not send the reset email.');
    } finally {
      setAuthBusy(false);
    }
  };

  const handleResetSubmit = async (e) => {
    if (e) e.preventDefault();
    if (resetPassword !== resetConfirm) {
      setAuthError('Those two passwords do not match.');
      return;
    }
    setAuthBusy(true);
    setAuthError(null);
    try {
      await api.confirmPasswordReset(resetToken, resetPassword);
      // The reset signed every device out, this one included, so anything
      // still in localStorage is a token the server has already deleted.
      localStorage.removeItem('token');
      localStorage.removeItem('tenant_id');
      setResetDone(true);
      setResetPassword('');
      setResetConfirm('');
    } catch (err) {
      setAuthError(err.message || 'Could not change your password.');
    } finally {
      setAuthBusy(false);
    }
  };

  const checkAuthSession = async () => {
    try {
      const user = await api.getMe();
      if (user) {
        setCurrentUser(user);
        setView('dashboard');
        if (user.role === 'Designer') {
          // Deliberately does not call fetchDashboardAndConfig: that pulls
          // customers, orders and financials into the browser session, and a
          // designer account has no legitimate use for any of it. The API
          // itself does not enforce this yet -- see
          // docs/design-management.md section 4 -- so this is the one real
          // containment step 7 actually has, and it is enforced by simply
          // never requesting the data rather than by trusting a permission
          // check that does not exist server-side.
          // The queue, not the upload folder: what a designer signs in for is
          // what has been asked of them.
          setDashboardTab('designWork');
          return;
        }
        if (isProductionStaff(user.role)) {
          setDashboardTab('assignments');
        } else {
          setDashboardTab('overview');
        }
        await fetchDashboardAndConfig(user);
      }
    } catch (e) {
      console.log("No saved session");
    } finally {
      setLoading(false);
    }
  };

  const getDrapedPreviewImage = (fabric, designUrl) => {
    const color = fabric?.color?.toLowerCase() || '';
    if (color.includes('rose') || color.includes('pink')) {
      return 'https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=600';
    }
    if (color.includes('gold') || color.includes('yellow')) {
      return 'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=600';
    }
    if (color.includes('black') || color.includes('charcoal')) {
      return 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=600';
    }
    if (color.includes('blue')) {
      return 'https://images.unsplash.com/photo-1539008835657-9e8e62c8425b?w=600';
    }
    if (color.includes('green') || color.includes('olive')) {
      return 'https://images.unsplash.com/photo-1605721911519-3dfeb3be25e7?w=600';
    }
    return 'https://images.unsplash.com/photo-1518049368264-7a13d7825d19?w=600';
  };

  // Each collection paints as soon as its own request lands rather than waiting on
  // the slowest one, and a failed request is reported instead of leaving the panel
  // looking like an empty boutique.
  const fetchDashboardAndConfig = async (user = currentUser) => {
    setLoading(true);
    setLoadErrors([]);

    const load = async (label, request, apply) => {
      try {
        const data = await request();
        if (apply && data !== undefined) apply(data);
      } catch (err) {
        console.error(`Failed to load ${label}`, err);
        setLoadErrors((prev) => (prev.includes(label) ? prev : [...prev, label]));
      }
    };

    await load('dashboard', api.getDashboard, (data) => {
      setDashboardData(data);
      if (data.recent_orders?.length > 0) {
        setSelectedDashboardOrder((current) => {
          if (!current) return data.recent_orders[0];
          return data.recent_orders.find(o => o.id === current.id) || current;
        });
      }
    });

    await load('customers', api.getCustomers, (data) => {
      setCustomersList(data);
      setAllCustomers(data);
    });

    await load('orders', api.getOrders, setOrdersList);

    // Dashboard, customers, orders and settings above and below ride ALWAYS_ON
    // or STRUCTURAL prefixes and always answer. These do not: /api/tailors/,
    // /api/scheduling/, /api/fabrics/, /api/boutique-designs/ and
    // /api/notifications/ each sit behind a module, and this ran them
    // unconditionally for every signed-in role -- so a Tailor, whose defaults
    // carry none of the first four, took four 403s on every single boot and
    // got four collections named in `loadErrors` as "could not load" for data
    // they were never meant to have. Same list the nav gates on, so a fetch
    // and its screen can no longer disagree about what this user has.
    if (hasModule(user, 'tailors')) await load('tailors', api.getTailors, setTailors);
    // The panel this fills says Upcoming, so it asks for upcoming: past
    // bookings and cancelled ones are history, not the day ahead.
    if (hasModule(user, 'scheduling')) await load('appointments', () => api.getAppointments({ upcoming: 'true' }), setAppointments);
    if (hasModule(user, 'fabrics')) await load('fabrics', api.getFabrics, setFabrics);
    if (hasModule(user, 'design_studio')) await load('designs', api.getAllBoutiqueDesigns, setAllDesigns);
    await load('settings', api.getBoutiqueSettings, (data) => {
      setBoutiqueSettings(data);
      setBoutiqueTimeZone(data?.timezone);
    });
    // Gateable like the four above, and the bell is on every screen -- but a
    // boutique that has switched notifications off has no bell to fill.
    if (hasModule(user, 'notifications')) await load('notifications', () => fetchNotifications(user), () => {});

    if (!user?.role || user.role === 'Owner') {
      await load('customer messages', api.getQueuedCustomerMessages, setQueuedMessages);
    }

    setLoading(false);
  };

  /** Record that the owner sent a queued message from their own WhatsApp. */
  // The linked WhatsApp session, read where it is shown. Quiet on failure:
  // a boutique with no session service configured must not see an error
  // banner on every dashboard visit.
  const fetchWhatsAppStatus = useCallback(async () => {
    try {
      const data = await api.getWhatsAppStatus();
      setWhatsappStatus({
        connected: !!data.connected,
        status: data.status || 'disconnected',
        qrCode: data.qrCode || null,
      });
    } catch {
      /* ignore silent background error */
    }
  }, []);

  useEffect(() => {
    if (view === 'dashboard' && dashboardTab === 'settings' && (!currentUser?.role || currentUser.role === 'Owner')) {
      fetchWhatsAppStatus();
    }
  }, [view, dashboardTab, currentUser, fetchWhatsAppStatus]);

  const handleMarkMessageSent = async (orderId, messageId) => {
    await api.markMessageSent(orderId, messageId);
    // The queue holds only what is still waiting, so a sent one leaves it.
    setQueuedMessages((prev) => prev.filter((m) => m.id !== messageId));
  };

  // Catalog Management Handlers
  // Photos picked in the modal, whether from the gallery or straight off the
  // camera, land here. Same handler for both inputs -- a capture and a pick
  // arrive as the same File.
  const handleSaveFabric = async (e) => {
    e.preventDefault();
    if (fabricSaving || fabricUploads) return;
    // A placement picked but never committed with "Add use" would file every
    // material in the group as uncategorised. Say so instead of saving.
    const unplaced = fabricGroups.findIndex((g) => !g.kind && !g.placements.length);
    if (unplaced >= 0) {
      alert(`Section ${unplaced + 1}: choose where these materials are used, `
        + 'then click "Add use".');
      return;
    }
    setFabricSaving(true);
    try {
      // One catalog row per material, carrying its group's placement. The
      // whitelist keeps UI-only fields (_id, materials) out of the payload.
      const rows = fabricGroups.flatMap((group) => group.materials.map((row) => ({
        name: row.name,
        material: row.material,
        color: row.color,
        color_hex: row.color_hex,
        is_available: row.is_available,
        kind: group.kind,
        variant: group.variant,
        price_per_meter: parseFloat(row.price_per_meter) || 0.00,
        image_urls: row.image_urls || [],
        image_url: row.image_url || (row.image_urls || [])[0]
          || 'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400',
        placements: group.placements.map(
          ({ garment, section, slot }) => ({ garment, section, slot })),
      })));
      if (editingFabric) {
        await api.updateFabric(editingFabric.id, rows[0]);
      } else {
        await api.createFabric(rows.length === 1 ? rows[0] : rows);
      }
      setShowFabricModal(false);
      setEditingFabric(null);
      setFabricGroups([blankGroup()]);
      fetchDashboardAndConfig();
    } catch (err) {
      alert("Failed to save fabric: " + err.message);
    } finally {
      setFabricSaving(false);
    }
  };

  const handleDeleteFabric = async (id) => {
    if (deletingFabricId) return;
    if (window.confirm("Are you sure you want to delete this fabric?")) {
      setDeletingFabricId(id);
      try {
        await api.deleteFabric(id);
        fetchDashboardAndConfig();
      } catch (err) {
        alert("Failed to delete fabric: " + err.message);
      } finally {
        setDeletingFabricId(null);
      }
    }
  };

  const blankAppointmentForm = {
    customer: '', appointment_type: 'TRIAL', scheduled_time: '',
    assigned_staff: '', notes: '', status: 'SCHEDULED',
  };

  /** Reload the panel under whichever view it is showing. */
  const reloadAppointments = async () => {
    const fresh = await api.getAppointments(
      showAllAppointments ? {} : { upcoming: 'true' });
    setAppointments(fresh);
  };

  /** Open one to look at it. A datetime-local input wants the boutique's own
   *  wall clock with no zone on the end, so the ISO string is trimmed to the
   *  minute after being read in local time. */
  const openAppointment = (appt) => {
    const when = new Date(appt.scheduled_time);
    const local = new Date(when.getTime() - when.getTimezoneOffset() * 60000)
      .toISOString().slice(0, 16);
    setEditingAppointment(appt);
    setAppointmentForm({
      customer: appt.customer,
      appointment_type: appt.appointment_type,
      scheduled_time: local,
      assigned_staff: appt.assigned_staff || '',
      notes: appt.notes || '',
      status: appt.status,
    });
    setShowAppointmentModal(true);
  };

  const closeAppointmentModal = () => {
    setShowAppointmentModal(false);
    setEditingAppointment(null);
    setAppointmentForm(blankAppointmentForm);
  };

  const handleSaveAppointment = async (e) => {
    e.preventDefault();
    if (savingAppointment) return;
    setSavingAppointment(true);
    try {
      const payload = {
        ...appointmentForm,
        assigned_staff: appointmentForm.assigned_staff || null,
        scheduled_time: new Date(appointmentForm.scheduled_time).toISOString(),
      };
      if (editingAppointment) {
        // The client cannot be moved to another person's appointment: that is
        // a different booking, not an edit of this one.
        delete payload.customer;
        await api.updateAppointment(editingAppointment.id, payload);
      } else {
        await api.createAppointment(payload);
      }
      await reloadAppointments();
      closeAppointmentModal();
    } catch (err) {
      alert((editingAppointment ? "Could not save the appointment: "
                                : "Could not book the appointment: ") + err.message);
    } finally {
      setSavingAppointment(false);
    }
  };

  /** Cancelling keeps the record and the reason it existed; it does not delete
   *  the customer's history. */
  const handleCancelAppointment = async () => {
    if (!editingAppointment) return;
    if (!window.confirm('Cancel this appointment? The customer keeps the record of it.')) return;
    setSavingAppointment(true);
    try {
      await api.updateAppointment(editingAppointment.id, { status: 'CANCELLED' });
      await reloadAppointments();
      closeAppointmentModal();
    } catch (err) {
      alert("Could not cancel the appointment: " + err.message);
    } finally {
      setSavingAppointment(false);
    }
  };

  const handleAssignWorkflow = async (orderId, updates) => {
    if (assigningWorkflowOrderId) return;
    setAssigningWorkflowOrderId(orderId);
    try {
      await api.updateOrder(orderId, updates);
      fetchDashboardAndConfig();
    } catch (err) {
      alert("Failed to update staff assignment: " + err.message);
    } finally {
      setAssigningWorkflowOrderId(null);
    }
  };

  const handleSaveDesign = async (e) => {
    e.preventDefault();
    if (designSaving) return;
    setDesignSaving(true);
    try {
      const payload = {
        ...designForm,
        price: parseFloat(designForm.price) || 0.00,
        is_boutique: designForm.is_boutique === true || designForm.is_boutique === 'true',
        // Only a complete position is sent; a half-chosen one would be refused.
        catalogue: designForm.catalogue_path || undefined,
      };
      delete payload.catalogue_path;
      if (!payload.image_url) {
        // Curated apparel image
        payload.image_url = 'https://images.unsplash.com/photo-1610030469668-93535c17b6b3?w=400';
      }
      if (editingDesign) {
        await api.updateBoutiqueDesign(editingDesign.id, payload);
      } else {
        await api.createBoutiqueDesign(payload);
      }
      setShowDesignModal(false);
      setEditingDesign(null);
      setDesignForm({ name: '', garment_type: 'Lehenga', neckline_style: '', sleeve_style: '', image_url: '', is_boutique: true, price: 0, description: '' });
      setDesignLibraryToken(t => t + 1);
      fetchDashboardAndConfig();
    } catch (err) {
      alert("Failed to save design: " + err.message);
    } finally {
      setDesignSaving(false);
    }
  };

  const handleDeleteDesign = async (id) => {
    if (window.confirm("Are you sure you want to delete this design?")) {
      try {
        await api.deleteBoutiqueDesign(id);
        setDesignLibraryToken(t => t + 1);
        fetchDashboardAndConfig();
      } catch (err) {
        alert("Failed to delete design: " + err.message);
      }
    }
  };

  // Auth Action Handlers
  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    if (authBusy) return;
    if (!loginEmail || !loginPassword) {
      alert("Please fill in all credentials.");
      return;
    }
    setAuthError(null);
    setAuthBusy(true);
    try {
      const res = await api.login(loginEmail, loginPassword);
      setCurrentUser(res.user);
      setView('dashboard');
      if (res.user.role === 'Designer') {
        // See the matching branch in checkAuthSession for why this skips
        // fetchDashboardAndConfig entirely rather than fetching and hiding.
        setDashboardTab('designWork');
        return;
      }
      if (isProductionStaff(res.user.role)) {
        setDashboardTab('assignments');
      } else {
        setDashboardTab('overview');
      }
      fetchDashboardAndConfig(res.user);
    } catch (err) {
      // Inline, not alert(): the comment on `authError` says these screens
      // deliberately do not put a modal dialog on top of a sign-in form, and
      // the forgot/reset views already follow that. Sign-in was the one that
      // still did -- worst on a phone, where the alert covers the form and
      // takes a second tap to clear before the password can be retyped.
      setAuthError(err.message || 'Invalid credentials.');
    } finally {
      setAuthBusy(false);
    }
  };

  const handleSignupSubmit = async (e) => {
    e.preventDefault();
    if (!signupForm.first_name || !signupForm.last_name || !signupForm.email_address || !signupForm.password) {
      alert("Please enter all required signup fields.");
      return;
    }
    setSignupStep(2); // Boutique details
  };

  const handleCompleteRegistration = async () => {
    // Signup creates a Postgres schema and runs every migration into it, which
    // takes seconds rather than milliseconds -- long enough that an owner who
    // hears nothing back presses the button again. The second press used to
    // start a second boutique; it now cannot start until the first has
    // answered.
    if (signupBusy) return;
    setSignupBusy(true);
    try {
      const res = await api.signup({
        first_name: signupForm.first_name,
        last_name: signupForm.last_name,
        email_address: signupForm.email_address,
        mobile_number: signupForm.mobile_number,
        password: signupForm.password,
        business_name: boutiqueName,
        business_address: boutiqueAddress
      });
      setCurrentUser(res.user);
      setSignupStep(3);
      setTimeout(() => {
        setView('dashboard');
        fetchDashboardAndConfig(res.user);
      }, 1500);
    } catch (err) {
      // Stays on this step and says so in the card. It used to alert() and
      // throw the owner back to step 1, so "that email is already registered"
      // -- much the commonest failure here -- read as the form having been
      // wiped for no stated reason.
      setSignupError(err.message || 'Registration failed.');
    } finally {
      setSignupBusy(false);
    }
  };

  const handleLogout = async () => {
    if (logoutBusy) return;
    setLogoutBusy(true);
    try {
      await api.logout();
      setCurrentUser(null);
      setView('login');
      setShowLogoutConfirm(false);
    } finally {
      setLogoutBusy(false);
    }
  };

  // Start Order Creation Flows
  const handleStartNewCustomer = () => {
    setCustomerId(null);
    setCustomerForm(DEFAULT_CUSTOMER_DATA);
    setProfilePhoto(null);
    setProfilePhotoPreview(null);
    setDesignNotes('');
    setDesignFiles([]);
    setDesignPreviews([]);
    setFabricFiles([]);
    setFabricPreviews([]);
    setSelectedFabric(null);
    setDrapingCompleted(false);
    setDrapingLoading(false);
    setShowDrapingModal(false);
    setSelectedTailor(null);
    setSelectedMaster(null);
    setDeliveryMethod('Direct Pickup');
    setCourierService('');
    setTrackingNumber('');
    setDeliveryAddress('');
    setGarmentJobs([]);
    setGarmentErrors({});
    setSelectionReviewPhase(false);
    setCurrentStep(1);
    setView('wizard');
  };

  const handleSelectExistingCustomer = async (cust) => {
    setShowSearchModal(false);
    setCustomerId(cust.id);
    setCustomerForm({
      ...DEFAULT_CUSTOMER_DATA,
      ...cust,
      measurements: cust.measurements || DEFAULT_CUSTOMER_DATA.measurements
    });
    setDesignNotes('');
    setDesignFiles([]);
    setDesignPreviews([]);
    setFabricFiles([]);
    setFabricPreviews([]);
    setSelectedFabric(null);
    setSelectedDesignTemplates([]);
    setDrapingCompleted(false);
    setDrapingLoading(false);
    setShowDrapingModal(false);
    setSelectedTailor(null);
    setSelectedMaster(null);
    setDeliveryMethod('Direct Pickup');
    setCourierService('');
    setTrackingNumber('');
    setDeliveryAddress('');
    setGarmentJobs([]);
    setGarmentErrors({});

    // Start from the beginning (Step 1: Dress/Garment Type)
    setSelectionReviewPhase(false);
    setCurrentStep(1);
    setView('wizard');
  };

  const openExistingCustomerModal = () => {
    setShowSearchModal(true);
  };

  // Wizard Step actions
  const handleBack = () => {
    if (currentStep === 6) {
      if (paymentPhase) {
        setPaymentPhase(false);
      } else {
        setCurrentStep(5);
      }
    } else if (currentStep === 2 && selectionReviewPhase) {
      setSelectionReviewPhase(false);
    } else if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    } else {
      setView('order-selector');
    }
  };

  const saveStep1 = async () => {
    // Step 1: AI Design Studio. Design choices & references ride on the draft.
    return persistDraft({ step: 2 });
  };

  const saveStep2 = async () => {
    // Step 2: Fabric Selection. Fabric choices ride on the draft.
    return persistDraft({ step: 3 });
  };

  const saveStep3 = async () => {
    // Step 3: Personal Details. Validate required contact information.
    const missing = [
      [!customerForm.first_name, 'First Name'],
      [!customerForm.last_name, 'Last Name'],
      [!customerForm.email_address, 'Email Address'],
      [!customerForm.mobile_number, 'Mobile Number'],
      [!customerForm.address, 'Address'],
    ].filter(([isMissing]) => isMissing).map(([, label]) => label);

    if (missing.length) {
      alert(`Please fill in: ${missing.join(', ')}.`);
      throw new Error("Validation failed");
    }

    return persistDraft({ step: 4 });
  };

  const saveStep4 = async () => {
    // Step 4: Measurements & Garments. Collect body measurements.
    const body = { ...(customerForm.measurements || {}) };
    const CUSTOMER_KEYS = {
      chest: 'bust', waist: 'waist', hip: 'hips', shoulder: 'shoulder', neck: 'neck',
    };
    garmentJobs.forEach(job => {
      Object.entries(CUSTOMER_KEYS).forEach(([templateKey, customerKey]) => {
        if (job.values[templateKey] !== undefined && job.values[templateKey] !== '') {
          body[customerKey] = job.values[templateKey];
        }
      });
    });
    setCustomerForm(prev => ({ ...prev, measurements: body }));
    return persistDraft({ step: 5 });
  };

  const submitOrderAndConfirm = async () => {
    setWizardError(null);

    // One request. The server creates the client, the order, its production
    // stages, its garments and their material lines inside a single
    // transaction, then spends the draft.
    //
    // What this replaces: create the order, then save the garments, then
    // attach the design, apologising after each step if it failed and pressing
    // on regardless -- because going back to press Confirm again booked a
    // SECOND order at the same price. Two invoices and doubled revenue from
    // one failed sub-step and one reasonable retry. Now a failure leaves no
    // order at all and the draft still on the server, so retrying is the right
    // thing to do rather than the dangerous one.
    let id = draftId;
    try {
      id = await persistDraft({ step: 6 });
    } catch (err) {
      setWizardError(
        err.isConflict
          ? 'This order was changed in another tab. Reload it before placing it.'
          : 'Could not save the order before placing it. Nothing has been booked — please try again.');
      return;
    }

    try {
      const order = await api.confirmOrderDraft(id);
      setDraftId(null);
      setDraftVersion(null);
      setDraftSaveState('idle');
      setConfirmedOrder(order);
      setView('confirmed');
      fetchDashboardAndConfig();
    } catch (err) {
      if (err.alreadyPlaced) {
        // A double-click, a retried request, or a refresh that re-fired it.
        // The order exists; the one thing that must not happen is booking a
        // second one, and the server has already refused to.
        setWizardError(
          'This order has already been placed. Check Manage Orders — do not place it again.');
        return;
      }
      console.error(err);
      setWizardError(
        (err.message || 'Could not place the order.')
        + ' Nothing was booked, and your order is still saved — you can try again.');
    }
  };
  const actionInFlight = useRef(false);
  const [ctaBusy, setCtaBusy] = useState(false);

  const runOnce = useCallback(async (action) => {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setCtaBusy(true);
    try {
      await action();
    } finally {
      actionInFlight.current = false;
      setCtaBusy(false);
    }
  }, []);

  // Orders already in progress, fetched when the owner arrives at the order
  // screen. Not on mount: a draft is only relevant at the point of starting or
  // resuming one, and asking for them on every dashboard load is a request
  // nobody reads.
  useEffect(() => {
    if (view !== 'order-selector') return;
    let cancelled = false;
    api.listOrderDrafts()
      .then(list => { if (!cancelled) setResumableDrafts(list || []); })
      .catch(err => {
        // A failure here costs the resume prompt, not the session.
        console.error('Could not load saved orders', err);
        if (!cancelled) setResumableDrafts([]);
      });
    return () => { cancelled = true; };
  }, [view]);

  const performNext = async () => {
    try {
      if (currentStep === 1) {
        await saveStep1();
        setCurrentStep(2);
      } else if (currentStep === 2) {
        const anyPartFabric = garmentJobs.some(job => Object.keys(job.fabrics || {}).length > 0);
        if (selectionReviewPhase) {
          // Confirm & Continue: the review has been read, on to the details.
          setSelectionReviewPhase(false);
          setCurrentStep(3);
          return;
        }
        if (fabricTab === 'boutique' && !selectedFabric && !anyPartFabric) {
          alert("Please select a fabric from the catalog or upload your own fabric.");
          return;
        }
        await saveStep2();
        setSelectionReviewPhase(true);
      } else if (currentStep === 3) {
        await saveStep3();
        setCurrentStep(4);
      } else if (currentStep === 4) {
        if (garmentJobs.length === 0) {
          alert("Please choose at least one garment for this order.");
          return;
        }
        if (!validateGarments()) {
          alert("Some garment details are missing or invalid — see the highlighted fields.");
          return;
        }
        await saveStep4();
        setCurrentStep(5);
      } else if (currentStep === 5) {
        if (!selectedTailor) {
          alert("Please assign a tailor for the creation.");
          return;
        }
        setCurrentStep(6);
      } else if (currentStep === 6) {
        if (!paymentPhase) {
          setPaymentPhase(true);
        } else {
          if (!agreedToTerms) {
            alert("Please agree to the Terms & Conditions and Privacy Policy before placing the order.");
            return;
          }
          await submitOrderAndConfirm();
        }
      }
    } catch (err) {
      console.error("Step execution failed", err);
      if (currentStep !== 1) {
        alert("Failed to proceed: " + err.message);
      }
    }
  };

  const performSaveDraft = async () => {
    try {
      if (currentStep === 1) {
        await saveStep1();
      } else if (currentStep === 2) {
        await saveStep2();
      } else if (currentStep === 3) {
        await saveStep3();
      } else if (currentStep === 4) {
        await saveStep4();
      }
      alert("Draft saved successfully!");
      setView('dashboard');
      fetchDashboardAndConfig();
    } catch (err) {
      console.error(err);
      alert("Failed to save draft.");
    }
  };

  const handleNext = () => runOnce(performNext);
  const handleSaveDraft = () => runOnce(performSaveDraft);

  // Image Upload Handlers
  const handleProfilePhotoChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setProfilePhoto(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setProfilePhotoPreview(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleFabricFilesChange = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
      setFabricFiles(prev => [...prev, ...files]);
      files.forEach(file => {
        const reader = new FileReader();
        reader.onloadend = () => {
          setFabricPreviews(prev => [...prev, reader.result]);
        };
        reader.readAsDataURL(file);
      });
    }
  };

  // Preview arithmetic only. The server recomputes all of this at confirm
  // through domains/orders/pricing.py and stores ITS answer; these exist so
  // the sidebar can show the owner the same number the server will reach.
  const PRICING_FIELDS = [
    ['base', 'Base price'], ['fabric', 'Fabric'], ['embroidery', 'Embroidery & work'],
    ['customization', 'Customization'], ['tailoring', 'Tailoring'],
  ];
  const jobSubtotal = (job) =>
    PRICING_FIELDS.reduce((sum, [key]) => sum + parseFloat(job.pricing?.[key] || 0), 0);
  const setJobPrice = (jobKey, field, value) => {
    setGarmentJobs(prev => prev.map(job => job.key === jobKey
      ? { ...job, pricing: { ...(job.pricing || {}), [field]: value } }
      : job));
  };

  const getSubtotal = () => {
    const garments = garmentJobs.reduce((sum, job) => sum + jobSubtotal(job), 0);
    const packaging = parseFloat(quotePrices.packaging || 0);
    const discount = parseFloat(quotePrices.discount || 0);
    return garments + packaging - discount;
  };

  const getTaxes = () => {
    return getSubtotal() * 0.05;
  };

  const getTotalPrice = () => {
    return getSubtotal() + getTaxes();
  };

  const getPasswordStrength = () => {
    const len = signupForm.password.length;
    if (len === 0) return '';
    if (len < 6) return 'weak';
    if (len < 10) return 'medium';
    return 'strong';
  };

  // Filter lists
  const filteredSearchModalCustomers = allCustomers.filter(c => {
    const fullName = `${c.first_name || ''} ${c.last_name || ''}`.toLowerCase();
    const query = searchModalQuery.toLowerCase();
    return fullName.includes(query) || (c.mobile_number || '').includes(query);
  });

  // Is this order mine to work on? The same three-way test core/permissions.py
  // visible_orders applies server-side: the order's tailor, its master, or a
  // stage assigned to me.
  //
  // The stage clause is the one that was missing. assign_stage exists precisely
  // so a supervisor can hand ONE stage to someone who is not the order's
  // tailor, and visible_orders deliberately returns that order to them -- but
  // this screen, which is the only screen a tailor has, threw it away and told
  // them "No active orders are assigned to you at the moment." Work was handed
  // out and the person was never told.
  /** A garment's shortlist changed.
   *
   *  Before Confirm this is the only home the selection has, so it goes on the
   *  garment in the draft payload -- the same place its spec, materials and
   *  price already live. After Confirm the board is real and this just tracks
   *  which board the order carries.
   */
  /** The parts a customer has chosen for one dress: {part_key: image}.
   *
   *  Kept on the garment job's own `design`, not in a state of its own. That is
   *  already what serialiseWizard writes to the draft and what the resume path
   *  reads back, so the selection persists, survives a refresh and comes back
   *  on resume without a second copy to keep in step.
   *
   *  Per garment, so a saree's Pallu and a blouse's Neck can never share a
   *  slot -- the parts are the garment's own, and mixing them across dresses is
   *  exactly the bug this shape prevents.
   */
  const partSelection = React.useMemo(
    () => Object.fromEntries(garmentJobs.map(job => [job.key, job.design?.parts || {}])),
    [garmentJobs]);

  const handlePartSelection = (garmentKey, next) => {
    setGarmentJobs(prev => prev.map(job => job.key === garmentKey
      ? { ...job, design: { ...(job.design || {}), parts: next } }
      : job));
  };

  /** The fabric chosen for each part of one dress: {slot_key: [fabric_id, ...]}.
   *
   *  Per garment AND per part, because that is what an order is: chanderi for
   *  the saree body, organza for its pallu, net for the blouse sleeves. One
   *  `selectedFabric` for the whole order could not say any of it.
   *
   *  A list per slot rather than a single id -- a sleeve takes net and its
   *  lining -- and kept on the garment job itself, so removing a dress takes
   *  its fabric choices with it and no stale blouse fabric can survive on an
   *  order that no longer has a blouse.
   */
  // The colour the boutique fabrics are narrowed to. Empty is every roll,
  // which is where the step opens; a swatch click or a typed word is the same
  // filter. Only the boutique tab reads it -- accessories and the customer's
  // own cloth are not filtered by it.
  const [fabricColorQuery, setFabricColorQuery] = useState('');
  const fabricSelection = React.useMemo(
    () => Object.fromEntries(garmentJobs.map(job => [job.key, job.fabrics || {}])),
    [garmentJobs]);

  const handleFabricSelection = (garmentKey, next) => {
    setGarmentJobs(prev => prev.map(job => job.key === garmentKey
      ? { ...job, fabrics: next }
      : job));
  };

  // What the boutique grid shows under a colour filter. A roll the customer
  // has already chosen stays on screen whatever the filter says: narrowing to
  // "red" must not make the blue lining they picked a minute ago vanish from
  // under its own tick, or they will pick it twice.
  const colourFilteredFabrics = React.useMemo(() => {
    const q = fabricColorQuery.trim().toLowerCase();
    if (!q) return fabrics;
    const chosen = new Set(
      Object.values(fabricSelection).flatMap(bySlot => Object.values(bySlot).flat()));
    return fabrics.filter(f =>
      fabricMatchesColour(f, q) || chosen.has(String(f.id)));
  }, [fabrics, fabricColorQuery, fabricSelection]);

  /** The customer's own references for one dress: {part_key: [reference, ...]}.
   *
   *  A list per part, not one: a customer describing the pallu they want sends
   *  three photographs of it and a Pinterest link, and picking which single one
   *  of those "counts" is the boutique's job, not something the form should
   *  force at the moment they are handing them over.
   *
   *  Kept beside `parts` on the same garment's `design` rather than inside it,
   *  so everything that already reads `parts` -- the summary, the modal, the
   *  board item written at Confirm -- keeps reading exactly one chosen
   *  photograph per part and is untouched by this.
   */
  const partReferences = React.useMemo(
    () => Object.fromEntries(garmentJobs.map(job => [job.key, job.design?.part_refs || {}])),
    [garmentJobs]);

  const handlePartReferences = (garmentKey, next) => {
    setGarmentJobs(prev => prev.map(job => job.key === garmentKey
      ? { ...job, design: { ...(job.design || {}), part_refs: next } }
      : job));
  };

  /** The stage this order is actually sitting on: the first one nobody has
   *  finished with, in the workflow's own declared order. */
  const liveStage = (order) => {
    const config = boutiqueSettings?.workflow_config || [];
    const status = Object.fromEntries(
      (order.stages || []).map(s => [s.stage_key, s.status]));
    return config.find(
      s => !['COMPLETED', 'SKIPPED'].includes(status[s.key] || 'NOT_STARTED')) || null;
  };

  const isMyAssignment = (order) => {
    const me = currentUser?.tailor_id;
    if (!me) return false;
    if (order.master === me
        || order.tailor === me
        || (order.stages || []).some(s => s.assigned_to === me)) return true;

    // Work that has reached a stage this role performs, which nobody had to
    // hand over first. The three clauses above are all personal attachment: a
    // QC Staff is never order.tailor (the stitcher) or order.master (the
    // supervisor), so before this the dashboard re-filtered the server's queue
    // straight back out and showed them nothing.
    //
    // Reads the stage's own `roles` -- the same list the server checks in
    // visible_orders and check_transition, and the same one
    // eligibleStaffForStage already reads here. One declaration, so this
    // cannot drift from what the API will actually allow.
    //
    // Owner and Master are excluded deliberately: every stage names them, so
    // including them would put the entire boutique under "My Assignments".
    // They see the floor through the order list, and their assignments stay
    // the work that is personally theirs -- which mirrors the server, where
    // supervisors return early and never consult the queue at all.
    if (currentUser?.role === 'Owner' || currentUser?.role === 'Master') return false;
    const live = liveStage(order);
    return !!live && (live.roles || []).includes(currentUser?.role);
  };

  // Opens the stage review panel for a given order and stage.
  const openStageReview = (order, stage) => {
    setActiveReviewStage(stage.stage_name);
    setActiveReviewOrder(order);
    setSelectedStageObj(stage);
    setStageReviewComments(stage.comments || '');
    setStageReviewImage(null);

    // Fetch the approved design for this order. Best-effort: a board that does
    // not exist is the normal case for an order placed without one, and must
    // not stop the stage panel from opening.
    setStageDesignBrief(null);
    setProductionNotesDraft('');
    api.getDesignBoards({ order_id: order.order_id })
      .then((boards) => {
        const brief = normaliseDesignBrief(
          Array.isArray(boards) ? boards[0] : boards);
        setStageDesignBrief(brief);
        setProductionNotesDraft(brief?.design?.production_notes || '');
      })
      .catch(() => setStageDesignBrief(null));
  };

  // The directory list returns flat rows without orders or measurement history,
  // so opening a client fetches the full record. The summary row is shown right
  // away and replaced in place, keeping the panel populated while it loads.
  const openDirectoryCustomer = async (summaryRow) => {
    setSelectedDirectoryCustomer(summaryRow);
    setDirectoryDetailLoading(true);
    try {
      const full = await api.getCustomer(summaryRow.id);
      setSelectedDirectoryCustomer((current) =>
        current && current.id === full.id ? full : current
      );
    } catch (err) {
      console.error('Failed to load customer detail', err);
    } finally {
      setDirectoryDetailLoading(false);
    }
  };

  // Staff the boutique's workflow allows on a given stage. Mirrors the server-side
  // check, so the dropdown never offers a choice the API would reject.
  const eligibleStaffForStage = (stageKey) => {
    const stageConf = (boutiqueSettings?.workflow_config || []).find(s => s.key === stageKey);
    const allowed = stageConf?.roles || [];
    if (allowed.length === 0) return tailors;
    return tailors.filter(t => allowed.includes(t.role));
  };

  // Who may actually be given the stitching.
  //
  // These pickers filtered `t.role !== 'Master'`, which passes every
  // specialist role -- Maggam, Karigar, Pressing and QC -- while
  // get_default_workflow restricts both
  // stitching stages to ["Owner", "Tailor"]. So the owner could hand the
  // stitching to the Maggam Master, the order was accepted, and that person
  // could see it and never advance it: transition_order_stage refuses their
  // role. The order sat until the owner worked out what had happened.
  //
  // eligibleStaffForStage reads the stage's own role list, which is the same
  // list the server checks, so the dropdown cannot offer a choice the API will
  // reject.
  const stitchingStaff = () => eligibleStaffForStage('stitching_in_progress');

  // Sign off a design. The detail record is refetched so the approved badge and the
  // superseded state of the other designs both come from the server, not a guess.
  const handleApproveDesign = async (prefId, fallbackImage) => {
    if (!selectedDirectoryCustomer) return;
    setApprovingDesignId(prefId);
    try {
      await api.approveDesign(selectedDirectoryCustomer.id, prefId, fallbackImage);
      const full = await api.getCustomer(selectedDirectoryCustomer.id);
      setSelectedDirectoryCustomer(current =>
        current && current.id === full.id ? full : current
      );
    } catch (err) {
      alert(err.message || 'Could not approve this design.');
    } finally {
      setApprovingDesignId(null);
    }
  };

  // Nominate who should perform a stage. The server refuses a role the stage does
  // not permit, so the error is surfaced rather than swallowed.
  const handleAssignStage = async (orderId, stageKey, tailorId) => {
    setAssigningStageKey(stageKey);
    try {
      await api.assignStage(orderId, stageKey, tailorId || null);
      await fetchDashboardAndConfig();
    } catch (err) {
      alert(err.message || 'Could not assign this stage.');
    } finally {
      setAssigningStageKey(null);
    }
  };

  // Customer Directory rows. Memoised because this was previously filtered twice
  // on every keystroke -- once for the empty check, once for the map.
  const directoryCustomers = React.useMemo(() => {
    const term = searchQuery.toLowerCase();
    return customersList.filter(cust => {
      const matchesSearch =
        ((cust.first_name || '') + ' ' + (cust.last_name || '')).toLowerCase().includes(term) ||
        (cust.mobile_number || '').includes(term) ||
        (cust.email_address || '').toLowerCase().includes(term);
      const matchesType =
        customerTypeFilter === 'All' ||
        (cust.customer_type || '').toLowerCase() === customerTypeFilter.toLowerCase();
      return matchesSearch && matchesType;
    });
  }, [customersList, searchQuery, customerTypeFilter]);

  if (globalError) {
    return (
      <div style={{ padding: '24px', background: '#7f1d1d', color: '#fef2f2', height: '100vh', fontFamily: 'monospace', overflowY: 'auto' }}>
        <h2 style={{ margin: '0 0 16px 0', fontSize: '20px' }}>Atelier CRM Runtime Error</h2>
        <pre style={{ whiteSpace: 'pre-wrap', fontSize: '14px', background: 'rgba(0,0,0,0.2)', padding: '16px', borderRadius: '8px' }}>
          {globalError}
        </pre>
        <button onClick={() => { localStorage.clear(); window.location.reload(); }} className="btn-secondary" style={{ marginTop: '16px', background: '#fff', color: '#7f1d1d', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: 'pointer' }}>
          Clear Session & Reload
        </button>
      </div>
    );
  }

  if (loading && !dashboardData && view === 'login') {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#0f291e', color: '#fff', fontSize: '18px', fontFamily: 'var(--font-sans, sans-serif)' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ border: '4px solid rgba(255,255,255,0.1)', borderTop: '4px solid #d4af37', borderRadius: '50%', width: '40px', height: '40px', animation: 'spin 1s linear infinite', margin: '0 auto 16px auto' }}></div>
          <span>Loading Atelier CRM...</span>
          <style>{`
            @keyframes spin {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      </div>
    );
  }


  // Driven by real data, so it can never disagree with the boutique's actual
  // state -- and it teaches the workflow in the order the work happens.
  const onboardingSteps = [
    { key: 'boutique', label: 'Create your boutique', done: true },
    { key: 'customer', label: 'Add your first customer', done: customersList.length > 0, go: () => setView('order-selector') },
    { key: 'order', label: 'Create your first order', done: ordersList.length > 0, go: () => setView('order-selector') },
    { key: 'staff', label: 'Add your staff (tailors & designers)', done: tailors.length > 0, tab: 'staff', go: () => setDashboardTab('staff') },
    { key: 'fabrics', label: 'Set up your fabric library', done: fabrics.length > 0, tab: 'fabrics', go: () => setDashboardTab('fabrics') },
    { key: 'production', label: 'Move an order through production', done: ordersList.some(o => o.order_status && o.order_status !== 'Received'), tab: 'orders', go: () => setDashboardTab('orders') },
    // A step whose screen this boutique cannot open is not a step it can ever
    // finish: `done` stays false forever, so the checklist never completes and
    // never stops nagging, and the arrow does nothing when clicked -- the
    // requested tab is gated, the derived dashboardTab keeps the old one, and
    // the row just sits there. Drop the instruction rather than give an
    // instruction that cannot be followed.
  ].filter((step) => !step.tab || canSeeTab(currentUser, step.tab));
  const showOnboarding = !loading && !onboardingDismissed && onboardingSteps.some(step => !step.done);
  return (
    <div className="app-container">
      {/* 2. SIGN IN SCREEN (Image 2) */}

      {view === 'login' && (
        <div className="auth-page" style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#faf9f6', padding: '88px 16px 40px' }}>
          
          {/* Back to Home Button */}
          <button 
            onClick={() => { window.location.href = '/'; }}
            style={{
              position: 'absolute',
              top: '30px',
              left: '5%',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: '#fff',
              border: '1px solid #eaecef',
              padding: '10px 18px',
              borderRadius: '99px',
              cursor: 'pointer',
              color: 'var(--text-secondary)',
              fontSize: '13px',
              fontWeight: '600',
              boxShadow: '0 2px 6px rgba(0,0,0,0.03)',
              transition: 'all 0.2s ease'
            }}
            onMouseOver={(e) => { e.currentTarget.style.borderColor = 'var(--accent-text, #b07c40)'; e.currentTarget.style.color = 'var(--accent-text, #b07c40)'; }}
            onMouseOut={(e) => { e.currentTarget.style.borderColor = '#eaecef'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
          >
            <ArrowLeft size={16} />
            Back to Home
          </button>

          <div className="auth-logo" style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', color: '#0f291e', fontWeight: 700, letterSpacing: '2px', marginBottom: '4px' }}>SCALEEZY</div>
          <div className="auth-logo-sub" style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px', marginBottom: '32px' }}>YOUR VISION. OUR CRAFT.</div>

          <div className="auth-card" style={{ maxWidth: '420px', width: '100%', background: '#fff', border: '1px solid #eaecef', borderRadius: '16px', padding: 'clamp(20px, 6vw, 40px)', boxShadow: '0 8px 30px rgba(0,0,0,0.02)' }}>
            <h2 className="auth-title" style={{ fontSize: '24px', color: '#0f291e', fontWeight: 600, margin: '0 0 8px 0' }}>Welcome back 👋</h2>
            <p className="auth-subtitle" style={{ fontSize: '13.5px', color: 'var(--text-secondary)', margin: '0 0 32px 0' }}>Login to continue your custom creation journey.</p>
            
            <form onSubmit={handleLoginSubmit} className="auth-form" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label className="form-label" style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Email</label>
                <div className="input-wrapper" style={{ position: 'relative' }}>
                  <Mail size={16} className="input-icon-left" style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                  <input 
                    type="text" 
                    placeholder="Enter your email"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    style={{ width: '100%', padding: '12px 14px 12px 42px', fontSize: '14px', borderRadius: '8px', border: '1px solid #eaecef', outline: 'none' }}
                    required
                  />
                </div>
              </div>

              <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label className="form-label" style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Password</label>
                <div className="input-wrapper" style={{ position: 'relative' }}>
                  <Lock size={16} className="input-icon-left" style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                  <input 
                    type={showLoginPassword ? "text" : "password"} 
                    placeholder="Enter your password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    style={{ width: '100%', padding: '12px 40px 12px 42px', fontSize: '14px', borderRadius: '8px', border: '1px solid #eaecef', outline: 'none' }}
                    required
                  />
                  <button 
                    type="button"
                    style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}
                    onClick={() => setShowLoginPassword(!showLoginPassword)}
                  >
                    {showLoginPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <div className="auth-remember-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '13px', margin: '6px 0 10px 0' }}>
                <span />
                <button
                  type="button"
                  className="forgot-password-link"
                  onClick={() => { setResetEmail(loginEmail); setResetSent(false); setAuthError(null); setView('forgot'); }}
                  style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--accent-text, #b07c40)', fontWeight: 600, fontSize: '13px', whiteSpace: 'nowrap' }}
                >
                  Forgot password?
                </button>
              </div>

              {authError && (
                <div role="alert" style={{ background: '#fdf2f2', border: '1px solid #f5c6c6', color: '#8a2020', borderRadius: '8px', padding: '10px 12px', fontSize: '13px' }}>
                  {authError}
                </div>
              )}

              <button type="submit" className="btn-primary" disabled={authBusy} style={{ justifyContent: 'center', padding: '14px', borderRadius: '8px', fontWeight: 600, fontSize: '14px', opacity: authBusy ? 0.6 : 1, cursor: authBusy ? 'wait' : 'pointer' }}>
                {authBusy ? 'Signing in…' : 'Login to Workspace'}
              </button>
            </form>

            <div className="auth-card-footer" style={{ borderTop: '1px solid #eaecef', marginTop: '32px', paddingTop: '20px', textAlign: 'center', fontSize: '13.5px', color: 'var(--text-secondary)' }}>
              Don't have a boutique account?{' '}
              <a href="#" style={{ color: 'var(--accent-text, #b07c40)', fontWeight: 600, textDecoration: 'none' }} onClick={() => { setSignupStep(1); setView('signup'); }}>
                Signup
              </a>
            </div>
          </div>
        </div>
      )}



      {/* 3. SIGN UP SCREEN (Image 3) */}
      {/* Ask for a reset link. Reached from the login screen; leaves back to
          it. Nothing here reveals whether the address is one we know. */}
      {view === 'forgot' && (
        <div className="auth-page" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#faf9f6', padding: '88px 16px 40px' }}>
          <div className="auth-card" style={{ background: '#fff', border: '1px solid #eaecef', borderRadius: '14px', padding: 'clamp(20px, 6vw, 36px)', width: '100%', maxWidth: '420px', boxShadow: '0 4px 20px rgba(0,0,0,0.04)' }}>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '22px' }}>Reset your password</h2>

            {resetSent ? (
              <>
                <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.6 }}>
                  If <strong>{resetEmail}</strong> has an account, a reset link is on its way.
                  It stops working in an hour. Check your spam folder if it has not arrived
                  in a few minutes.
                </p>
                <button type="button" className="btn-primary" style={{ width: '100%', justifyContent: 'center', padding: '13px', borderRadius: '8px', fontWeight: 600 }} onClick={() => { setResetSent(false); setView('login'); }}>
                  Back to sign in
                </button>
              </>
            ) : (
              <form onSubmit={handleForgotSubmit}>
                <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.6, marginTop: 0 }}>
                  Enter the email address you sign in with and we will send you a link to
                  choose a new password.
                </p>
                <input
                  type="email"
                  autoFocus
                  value={resetEmail}
                  onChange={(e) => setResetEmail(e.target.value)}
                  placeholder="you@yourboutique.com"
                  style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid #eaecef', fontSize: '14px', marginBottom: '12px', boxSizing: 'border-box' }}
                />
                {authError && (
                  <div role="alert" style={{ background: '#fdf2f2', border: '1px solid #f5c6c6', color: '#8a2020', borderRadius: '8px', padding: '10px 12px', fontSize: '13px', marginBottom: '12px' }}>
                    {authError}
                  </div>
                )}
                <button type="submit" className="btn-primary" disabled={authBusy} style={{ width: '100%', justifyContent: 'center', padding: '13px', borderRadius: '8px', fontWeight: 600, opacity: authBusy ? 0.6 : 1, cursor: authBusy ? 'wait' : 'pointer' }}>
                  {authBusy ? 'Sending…' : 'Send reset link'}
                </button>
                <button type="button" onClick={() => { setAuthError(null); setView('login'); }} style={{ width: '100%', marginTop: '10px', background: 'none', border: 'none', color: 'var(--text-secondary)', fontSize: '13px', cursor: 'pointer' }}>
                  Back to sign in
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Choose the new password. Only reachable by following the emailed
          link, which is what put resetToken in state. */}
      {view === 'reset' && (
        <div className="auth-page" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#faf9f6', padding: '88px 16px 40px' }}>
          <div className="auth-card" style={{ background: '#fff', border: '1px solid #eaecef', borderRadius: '14px', padding: 'clamp(20px, 6vw, 36px)', width: '100%', maxWidth: '420px', boxShadow: '0 4px 20px rgba(0,0,0,0.04)' }}>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '22px' }}>Choose a new password</h2>

            {resetDone ? (
              <>
                <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.6 }}>
                  Your password has been changed, and every device that was signed in to
                  this account has been signed out.
                </p>
                <button type="button" className="btn-primary" style={{ width: '100%', justifyContent: 'center', padding: '13px', borderRadius: '8px', fontWeight: 600 }} onClick={() => { setResetDone(false); setResetToken(null); setView('login'); }}>
                  Sign in
                </button>
              </>
            ) : (
              <form onSubmit={handleResetSubmit}>
                <input
                  type="password"
                  autoFocus
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                  placeholder="New password"
                  style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid #eaecef', fontSize: '14px', marginBottom: '10px', boxSizing: 'border-box' }}
                />
                <input
                  type="password"
                  value={resetConfirm}
                  onChange={(e) => setResetConfirm(e.target.value)}
                  placeholder="Repeat new password"
                  style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid #eaecef', fontSize: '14px', marginBottom: '12px', boxSizing: 'border-box' }}
                />
                {authError && (
                  <div role="alert" style={{ background: '#fdf2f2', border: '1px solid #f5c6c6', color: '#8a2020', borderRadius: '8px', padding: '10px 12px', fontSize: '13px', marginBottom: '12px', whiteSpace: 'pre-wrap' }}>
                    {authError}
                  </div>
                )}
                <button type="submit" className="btn-primary" disabled={authBusy} style={{ width: '100%', justifyContent: 'center', padding: '13px', borderRadius: '8px', fontWeight: 600, opacity: authBusy ? 0.6 : 1, cursor: authBusy ? 'wait' : 'pointer' }}>
                  {authBusy ? 'Saving…' : 'Change password'}
                </button>
                <button type="button" onClick={() => { setAuthError(null); setResetToken(null); setView('login'); }} style={{ width: '100%', marginTop: '10px', background: 'none', border: 'none', color: 'var(--text-secondary)', fontSize: '13px', cursor: 'pointer' }}>
                  Back to sign in
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {view === 'signup' && (
        <div className="auth-page" style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#faf9f6', padding: '88px 16px 40px' }}>
          
          {/* Back to Home Button */}
          <button 
            onClick={() => { window.location.href = '/'; }}
            style={{
              position: 'absolute',
              top: '30px',
              left: '5%',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: '#fff',
              border: '1px solid #eaecef',
              padding: '10px 18px',
              borderRadius: '99px',
              cursor: 'pointer',
              color: 'var(--text-secondary)',
              fontSize: '13px',
              fontWeight: '600',
              boxShadow: '0 2px 6px rgba(0,0,0,0.03)',
              transition: 'all 0.2s ease'
            }}
            onMouseOver={(e) => { e.currentTarget.style.borderColor = 'var(--accent-text, #b07c40)'; e.currentTarget.style.color = 'var(--accent-text, #b07c40)'; }}
            onMouseOut={(e) => { e.currentTarget.style.borderColor = '#eaecef'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
          >
            <ArrowLeft size={16} />
            Back to Home
          </button>

          <div className="auth-logo" style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', color: '#0f291e', fontWeight: 700, letterSpacing: '2px', marginBottom: '4px' }}>SCALEEZY</div>
          <div className="auth-logo-sub" style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1.5px', marginBottom: '32px' }}>YOUR VISION. OUR CRAFT.</div>

          {/* Auth Steps Tracker */}
          <div className="auth-steps-tracker">
            {/* Was five steps, two of which were scenery.
                "Verify" showed an OTP box under "We have sent a 6-digit OTP
                code to +91 <number>". Nothing was ever sent -- no SMS
                provider exists in this product -- and handleVerifyOTP checked
                only that the field was non-empty, so any six characters, or
                any one character, walked through. It taught a new owner that
                the number they typed had been confirmed when it had not.
                "Preferences" listed six style tags as plain <span>s: no
                onClick, no state, nothing saved anywhere, and a heading
                asking the owner to select from them.
                Both are gone rather than implemented. Real mobile
                verification is an SMS provider, a cost per message and a
                resend/expiry flow; style tags are a feature nothing in the
                product reads yet. Neither is a fix for a fake step. */}
            {[
              { step: 1, label: 'Account' },
              { step: 2, label: 'Boutique' },
              { step: 3, label: 'Complete' }
            ].map(item => (
              <div key={item.step} className={`auth-step-item ${signupStep === item.step ? 'active' : ''}`}>
                <div className="auth-step-num">{item.step}</div>
                <span className="auth-step-label">{item.label}</span>
              </div>
            ))}
          </div>

          <div className="auth-card">
            {signupStep === 1 && (
              <>
                <h2 className="auth-title">Create your account</h2>
                <p className="auth-subtitle">Join Scaleezy and start your custom creation journey.</p>
                
                <form onSubmit={handleSignupSubmit} className="auth-form">
                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">First Name</label>
                      <input 
                        type="text" 
                        placeholder="Enter first name"
                        value={signupForm.first_name}
                        onChange={(e) => setSignupForm({...signupForm, first_name: e.target.value})}
                        required
                        className="form-control"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Last Name</label>
                      <input 
                        type="text" 
                        placeholder="Enter last name"
                        value={signupForm.last_name}
                        onChange={(e) => setSignupForm({...signupForm, last_name: e.target.value})}
                        required
                        className="form-control"
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Email Address</label>
                    <input 
                      type="email" 
                      placeholder="Enter your email address"
                      value={signupForm.email_address}
                      onChange={(e) => setSignupForm({...signupForm, email_address: e.target.value})}
                      required
                      className="form-control"
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Mobile Number</label>
                    <div className="input-wrapper">
                      <span className="input-icon-left" style={{ left: '12px', fontSize: '14px' }}>+91</span>
                      <input 
                        type="tel" 
                        placeholder="Enter mobile number"
                        value={signupForm.mobile_number}
                        onChange={(e) => setSignupForm({...signupForm, mobile_number: e.target.value})}
                        style={{ paddingLeft: '50px' }}
                        required
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Password</label>
                    <input 
                      type="password" 
                      placeholder="Create a password (min 6 characters)"
                      value={signupForm.password}
                      onChange={(e) => setSignupForm({...signupForm, password: e.target.value})}
                      required
                      className="form-control"
                    />
                    {signupForm.password && (
                      <div className="password-strength-meter">
                        <div className="password-strength-bar">
                          <div className={`password-strength-fill ${getPasswordStrength()}`}></div>
                        </div>
                        <span className="password-strength-text">
                          Password strength: <span>{getPasswordStrength()}</span>
                        </span>
                      </div>
                    )}
                  </div>

                  <label className="remember-me-checkbox" style={{ fontSize: '12px' }}>
                    <input type="checkbox" required />
                    I agree to the Terms & Conditions and Privacy Policy
                  </label>

                  <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginTop: '12px' }}>
                    <button type="button" className="btn-secondary" style={{ justifyContent: 'center' }} onClick={() => setView('login')}>
                      Login
                    </button>
                    <button type="submit" className="btn-primary" style={{ justifyContent: 'center' }}>
                      Create Account
                    </button>
                  </div>
                </form>

                <div className="divider-container">OR CONTINUE WITH</div>
                <div className="social-icons-row">
                  <div className="social-icon-circle"><Compass size={18} /></div>
                  <div className="social-icon-circle"><User size={18} /></div>
                  <div className="social-icon-circle"><MessageSquare size={18} /></div>
                </div>
              </>
            )}

            {signupStep === 2 && (
              <>
                <h2 className="auth-title">Your Boutique</h2>
                <p className="auth-subtitle">This is what your customers see on invoices and messages.</p>

                {/* This step used to ask for an occupation and a preferred
                    communication channel. Neither was read by anything -- the
                    signup view bound one of them and never mentioned it again
                    -- while the two fields the product genuinely prints on
                    every invoice, the boutique's name and address, were never
                    asked for at all and fell back to "123 Atelier Way, Fashion
                    District". Same step, same number of fields, now feeding
                    BoutiqueSettings. */}
                <div className="auth-form">
                  <div className="form-group">
                    <label className="form-label">Boutique name</label>
                    <input
                      type="text"
                      placeholder="e.g. Aditi's Atelier"
                      className="form-control"
                      value={boutiqueName}
                      onChange={(e) => setBoutiqueName(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Boutique address</label>
                    <input
                      type="text"
                      placeholder="Street, area, city, PIN"
                      className="form-control"
                      value={boutiqueAddress}
                      onChange={(e) => setBoutiqueAddress(e.target.value)}
                    />
                  </div>

                  {signupError && (
                    <div role="alert" style={{ background: '#fdf2f2', border: '1px solid #f5c6c6', color: '#8a2020', borderRadius: '8px', padding: '10px 12px', fontSize: '13px', marginBottom: '4px', whiteSpace: 'pre-wrap' }}>
                      {signupError}
                    </div>
                  )}
                  <button className="btn-primary" style={{ justifyContent: 'center' }} disabled={signupBusy} onClick={handleCompleteRegistration}>
                    {signupBusy ? 'Creating your boutique…' : 'Create my boutique'}
                  </button>
                  <button type="button" className="btn-secondary" style={{ justifyContent: 'center' }} onClick={() => setSignupStep(1)}>
                    Back
                  </button>
                </div>
              </>
            )}

            {signupStep === 3 && (
              <div style={{ textAlign: 'center', padding: '32px' }}>
                <div className="success-circle" style={{ margin: '0 auto 20px' }}><Check size={36} /></div>
                <h2 className="auth-title">Registration Complete!</h2>
                <p style={{ color: 'var(--text-secondary)' }}>Welcome to Scaleezy. Redirecting you to the portal workspace...</p>
              </div>
            )}
          </div>

          <div className="auth-badge-info-grid">
            <div className="auth-badge-card">
              <Lock className="auth-badge-icon" size={24} />
              <h4>Secure & Encrypted</h4>
              <p>Your data is protected with enterprise-tier bank level security standards.</p>
            </div>
            <div className="auth-badge-card">
              <Compass className="auth-badge-icon" size={24} />
              <h4>Personalized Experience</h4>
              <p>Tailored custom order builders matching style flows perfectly.</p>
            </div>
            <div className="auth-badge-card">
              <Star className="auth-badge-icon" size={24} />
              <h4>Expert Support</h4>
              <p>Boutique assistance is available 24/7 at the click of a button.</p>
            </div>
          </div>
        </div>
      )}

      {/* 4. BOUTIQUE PORTAL MAIN WORKSPACE (Image 4) */}
      {view === 'dashboard' && currentUser && (
        <div className={`portal-layout${navCollapsed ? ' nav-collapsed' : ''}`}>
          <MobileHeader
            title={t(
              dashboardTab === 'overview' ? 'nav.dashboard' :
              dashboardTab === 'orders' ? 'nav.manageOrders' :
              dashboardTab === 'fabrics' ? 'nav.manageFabrics' :
              dashboardTab === 'tailors' ? 'nav.manageTailors' :
              dashboardTab === 'designs' ? 'nav.manageDesigns' :
              `nav.${dashboardTab}`,
              dashboardTab.charAt(0).toUpperCase() + dashboardTab.slice(1)
            )}
            currentUser={currentUser}
            notificationsCount={notifications.filter(n => !n.is_read).length}
            onOpenMenu={() => setMobileNavOpen(!mobileNavOpen)}
            onOpenNotifications={() => {
              setShowNotificationsDrawer(true);
              if (markingNotificationsRead) return;
              setMarkingNotificationsRead(true);
              api.markNotificationsAsRead(currentUser.role || 'Owner', currentUser.email)
                .then(() => fetchNotifications())
                    // Never let the bell take the app down: a refused or failed
                    // mark-read is not worth losing the session over.
                    .catch(() => {})
                    .finally(() => setMarkingNotificationsRead(false));
            }}
          />

          {/* Mobile Top Header with Hamburger Toggle */}
          <div className="mobile-portal-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <button 
                type="button" 
                className="mobile-hamburger-btn"
                onClick={() => setMobileNavOpen(!mobileNavOpen)}
                aria-label="Toggle navigation menu"
              >
                {mobileNavOpen ? <X size={22} /> : <Menu size={22} />}
              </button>
              <div>
                <div className="portal-sidebar-logo" style={{ fontSize: '18px' }}>SCALEEZY</div>
                <div className="portal-sidebar-logo-sub" style={{ fontSize: '9px' }}>THE ATELIER EXPERIENCE</div>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                disabled={markingNotificationsRead}
                onClick={() => {
                  setShowNotificationsDrawer(true);
                  if (markingNotificationsRead) return;
                  setMarkingNotificationsRead(true);
                  api.markNotificationsAsRead(currentUser.role || 'Owner', currentUser.email)
                    .then(() => fetchNotifications())
                    // Never let the bell take the app down: a refused or failed
                    // mark-read is not worth losing the session over.
                    .catch(() => {})
                    .finally(() => setMarkingNotificationsRead(false));
                }}
                className="btn-secondary"
                style={{ padding: '6px 10px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Bell size={14} />
                {notifications.filter(n => !n.is_read).length > 0 && (
                  <span style={{ backgroundColor: '#ff4d4d', color: '#fff', borderRadius: '10px', padding: '1px 6px', fontSize: '10px', fontWeight: 700 }}>
                    {notifications.filter(n => !n.is_read).length}
                  </span>
                )}
              </button>
            </div>
          </div>

          {/* Backdrop overlay when mobile nav is open */}
          {mobileNavOpen && (
            <div className="mobile-portal-overlay" onClick={() => setMobileNavOpen(false)} />
          )}

          {/* Sidebar */}
          <aside className={`portal-sidebar ${mobileNavOpen ? 'mobile-open' : ''}`}>
            <div className="portal-sidebar-header-desktop">
              <div className="portal-sidebar-brand">
                <div>
                  <div className="portal-sidebar-logo">SCALEEZY</div>
                  <div className="portal-sidebar-logo-sub">THE ATELIER EXPERIENCE</div>
                </div>
                <div className="portal-sidebar-mark" aria-hidden="true">S</div>
                <button type="button" className="portal-nav-toggle" onClick={toggleNav}
                        aria-label={navCollapsed ? 'Expand navigation' : 'Collapse navigation'}
                        aria-expanded={!navCollapsed}
                        title={navCollapsed ? 'Expand navigation' : 'Collapse navigation'}>
                  {navCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
                </button>
              </div>
            </div>


            <nav className="portal-menu">
              <PortalMenu
                sections={navSections}
                activeTab={dashboardTab}
                collapsed={navCollapsed && !mobileNavOpen}
                onPick={(tab) => { setDashboardTab(tab); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}
              />
              <NavItem icon={LogOut} label={t('nav.logout')} collapsed={navCollapsed && !mobileNavOpen}
                       onClick={() => { setShowLogoutConfirm(true); setMobileNavOpen(false); }} />
            </nav>


          </aside>

          {/* Main Content Area */}
          <main className="portal-main">
            {dashboardTab === 'assignments' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        My Assignments Dashboard
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                        Logged in as {currentUserName} ({currentUser.role}). View and manage your active orders.
                      </p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(currentUserName)}`} alt="Avatar" />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  </div>
                </header>

                <div className="tailor-manager-content" style={{ marginTop: '24px' }}>
                  <div style={{
                    background: 'var(--surface-color)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '12px',
                    padding: '24px'
                  }}>
                    <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
                      Active Assigned Orders
                    </h3>
                    
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      {ordersList.filter(o => 
                        isMyAssignment(o)
                      ).length === 0 ? (
                        <p style={{ color: 'var(--text-muted)', padding: '16px 0', textAlign: 'center', fontSize: '13px' }}>
                          No active orders are assigned to you at the moment.
                        </p>
                      ) : (
                        ordersList.filter(o => 
                          isMyAssignment(o)
                        ).map(order => (
                          <div key={order.id} style={{
                            background: 'rgba(0,0,0,0.01)',
                            border: '1px solid var(--border-color)',
                            borderRadius: '12px',
                            padding: '20px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '12px'
                          }}>
                            {/* Order Header */}
                            <div className="assignment-card-header">
                              <div>
                                <span style={{ fontWeight: 700, fontSize: '16px', color: 'var(--text-primary)' }}>Order ID: {orderRef(order)}</span>
                                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                                  Client: {order.customer_name} | Est. Delivery: {order.estimated_delivery ? fmtDate(order.estimated_delivery) : 'TBD'}
                                </div>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                                <span className={`order-row-badge ${order.order_status.toLowerCase().replace(/ & /g, '_').replace(/ /g, '_')}`} style={{ fontSize: '11px', padding: '3px 10px' }}>
                                  {order.order_status}
                                </span>
                                <select
                                  className="form-control"
                                  style={{ fontSize: '12px', padding: '4px 10px', width: '160px', margin: 0 }}
                                  value={order.order_status}
                                  disabled={updatingStatusOrderId === order.id}
                                  onChange={(e) => {
                                    if (updatingStatusOrderId) return;
                                    setUpdatingStatusOrderId(order.id);
                                    api.updateOrderStatus(order.id, e.target.value)
                                      .then(() => fetchDashboardAndConfig())
                                      .catch(err => alert("Failed to update status: " + err.message))
                                      .finally(() => setUpdatingStatusOrderId(null));
                                  }}
                                >
                                  <option value="Received">Received</option>
                                  <option value="Confirmed">Confirmed</option>
                                  <option value="Stylist Review">Stylist Review</option>
                                  <option value="Design & Creation">Design & Creation</option>
                                  <option value="Quality Check">Quality Check</option>
                                  <option value="Ready for Dispatch">Ready for Dispatch</option>
                                  <option value="Shipped">Shipped</option>
                                  <option value="Delivered">Delivered</option>
                                </select>
                              </div>
                            </div>
                            
                            {/* Price / Scope */}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', background: 'var(--surface-color)', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                              <div className="assignment-card-sub-info" style={{ borderBottom: (!isProductionStaff(currentUser.role) || order.customer_measurements || (order.garment_jobs || []).length > 0) ? '1px solid var(--border-color)' : 'none', paddingBottom: '10px', fontSize: '13px' }}>
                                {!isProductionStaff(currentUser.role) && <div>Total Value: <span style={{ fontWeight: 600 }}>₹{parseFloat(order.total_amount).toLocaleString()}</span></div>}
                                <div>Assigned Supervising Master: <span style={{ fontWeight: 600, color: 'var(--accent-text, #b07c40)' }}>{order.master_name || 'Unassigned'}</span></div>
                                <div>Assigned Stitching Tailor: <span style={{ fontWeight: 600 }}>{order.tailor_name || 'Unassigned'}</span></div>
                              </div>

                              {/* What this order is for, per garment.
                                  This panel used to print order.customer_garment_type and the
                                  customer-level Measurement row. Both are single-valued and the
                                  order is not: a blouse-and-lehenga order named one garment, and
                                  the roll-up that fed the numbers keeps whichever dress was
                                  entered last -- so the tailor was shown the lehenga's waist for
                                  the blouse, and blouse length, upper chest, armhole and floor
                                  length were absent entirely because they are not rolled up.
                                  Read the garment jobs, which hold exactly what was ordered. */}
                              {(order.garment_jobs || []).length > 0 ? (
                                <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                  <div className="assignment-card-blueprint-header" style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                    <span>
                                      {order.garment_jobs.length > 1 ? 'Garments' : 'Garment'}:{' '}
                                      <span style={{ color: 'var(--accent-text, #b07c40)' }}>{orderGarmentLabel(order)}</span>
                                    </span>
                                    <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)' }}>📏 Measurements as ordered</span>
                                  </div>
                                  {order.garment_jobs.map(job => {
                                    const entries = Object.entries(job.measurements || {})
                                      .filter(([, v]) => v !== '' && v !== null && v !== undefined);
                                    return (
                                      <div key={job.id}>
                                        <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                                          {job.template_name || job.template_key}
                                        </div>
                                        {entries.length > 0 ? (
                                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '8px', background: 'rgba(0,0,0,0.015)', padding: '8px', borderRadius: '6px' }}>
                                            {entries.map(([k, v]) => (
                                              <div key={k}>{humaniseSpecKey(k)}: <strong>{String(v)} in</strong></div>
                                            ))}
                                          </div>
                                        ) : (
                                          <div style={{ padding: '8px', background: 'rgba(0,0,0,0.015)', borderRadius: '6px' }}>
                                            No measurements were captured for this garment.
                                          </div>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              ) : order.customer_measurements && (
                                /* Orders written before garment jobs existed. Nine of the ten
                                   orders already in the database are in this state, so the old
                                   panel stays reachable rather than showing them nothing. */
                                <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                                  <div className="assignment-card-blueprint-header" style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                    <span>
                                      Dress / Garment Type: <span style={{ color: 'var(--accent-text, #b07c40)' }}>{orderGarmentLabel(order)}</span>
                                      {(() => {
                                        const parts = order.customer_measurements.additional_measurements?.stitch_parts || [];
                                        return parts.length > 0 && ` (${parts.join(', ')})`;
                                      })()}
                                    </span>
                                    <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)' }}>📍 Customer measurements on file</span>
                                  </div>
                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: '8px', background: 'rgba(0,0,0,0.015)', padding: '8px', borderRadius: '6px' }}>
                                    {(() => {
                                      const parts = order.customer_measurements.additional_measurements?.stitch_parts || [];
                                      const visible = getVisibleMeasurementFields(parts);
                                      return (
                                        <>
                                          {visible.includes('bust') && <div>Bust: <strong>{order.customer_measurements.bust || '—'} in</strong></div>}
                                          {visible.includes('waist') && <div>Waist: <strong>{order.customer_measurements.waist || '—'} in</strong></div>}
                                          {visible.includes('hips') && <div>Hips: <strong>{order.customer_measurements.hips || '—'} in</strong></div>}
                                          {visible.includes('shoulder') && <div>Shoulder: <strong>{order.customer_measurements.shoulder || '—'} in</strong></div>}
                                          {visible.includes('arm_length') && <div>Arm: <strong>{order.customer_measurements.arm_length || '—'} in</strong></div>}
                                          {visible.includes('neck') && <div>Neck: <strong>{order.customer_measurements.neck || '—'} in</strong></div>}
                                          {visible.includes('length') && <div>Length: <strong>{order.customer_measurements.length || '—'} in</strong></div>}
                                        </>
                                      );
                                    })()}
                                  </div>
                                </div>
                              )}
                            </div>

                            {/* Production stages -- a master runs most of the
                                workflow, so the tracker belongs on the screen
                                they land on, not only on the order registry. */}
                            {/* Everyone who works the floor, not just supervisors.
                                stitching_in_progress is one of only two stages a
                                Tailor is authorised on, and this gate was the
                                reason no screen in the product let them touch it:
                                their nav offers only My Assignments and My
                                Account, and the timeline is the sole control that
                                posts a transition. Their stage never left
                                NOT_STARTED, so the record said the garment was
                                finished without ever being started, and the order
                                stayed IN_PROGRESS after delivery until an Owner
                                unstuck it. Opening the panel is safe for any
                                role: transition_order_stage refuses every stage
                                their role does not list, and the modal's Assign
                                and Record-performer selects carry their own
                                supervisor gates. */}
                            <div>
                              <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '2px' }}>
                                Production Stages — select a stage to update
                              </div>
                              <StageTimeline
                                stages={order.stages}
                                onSelectStage={(stage) => openStageReview(order, stage)}
                              />
                            </div>

                             {/* Delivery Information */}
                            <div style={{ fontSize: '13px', background: 'rgba(0,0,0,0.01)', padding: '12px', borderRadius: '8px', border: '1px dashed var(--border-color)', marginTop: '4px' }}>
                              <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>Delivery Method: {order.delivery_method}</div>
                              {order.delivery_method === 'Courier' && (
                                <div style={{ color: 'var(--text-secondary)' }}>
                                  <strong>Courier Service:</strong> {order.courier_service || 'TBD'} | 
                                  <strong> Tracking #:</strong> {order.tracking_number || 'TBD'}
                                  {order.delivery_address && (
                                    <div style={{ marginTop: '4px' }}><strong>Shipping Address:</strong> {order.delivery_address}</div>
                                  )}
                                </div>
                              )}
                            </div>

                            {/* The same gathering checklist, on the card the
                                Master actually works from. */}
                            <div style={{ marginTop: '12px', padding: '14px 16px', border: '1px solid var(--border-color)', borderRadius: '8px', textAlign: 'left' }}>
                              <h4 style={{ fontSize: '13px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '6px' }}>
                                🧵 Raw Materials Checklist
                              </h4>
                              <MaterialsChecklist orderId={order.id} role={currentUser.role} />
                            </div>

                            {/* Master Verification Checklist */}
                            {currentUser.role === 'Master' && (
                              <div style={{
                                marginTop: '12px',
                                padding: '16px',
                                background: 'rgba(212,175,55,0.03)',
                                border: '1px solid rgba(212,175,55,0.15)',
                                borderRadius: '8px',
                                textAlign: 'left'
                              }}>
                                <h4 style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 12px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                  👑 Master Production Verification Checklist
                                </h4>
                                
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '8px 16px' }}>
                                  {[
                                    { key: 'dress_cutting', label: 'Dress & Pattern Cutting' },
                                    { key: 'thread', label: 'Matching Thread & Accents' },
                                    { key: 'hemming', label: 'Hemming & Seam Finishes' },
                                    // Any saree on the order needs fall & pico, not just an
                                    // order whose customer record happens to say 'Saree'.
                                    ...(orderGarmentNames(order).includes('Saree') ? [{ key: 'fall_pico', label: 'Fall & Pico / Peack' }] : []),
                                    { key: 'hook_buttons', label: 'Hook or Buttons Closure' },
                                    { key: 'pressing', label: 'Garment Steam Pressing' },
                                    { key: 'dispatch_trial', label: 'Dispatch or Fit Trial Ready' }
                                  ].map(item => {
                                    const isChecked = order.master_verification?.[item.key] || false;
                                    return (
                                      <label key={item.key} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12.5px', cursor: 'pointer', color: 'var(--text-secondary)' }}>
                                        <input
                                          type="checkbox"
                                          checked={isChecked}
                                          disabled={savingVerificationOrderId === order.id}
                                          onChange={async (e) => {
                                            if (savingVerificationOrderId) return;
                                            const updatedVerification = {
                                              ...(order.master_verification || {}),
                                              [item.key]: e.target.checked
                                            };
                                            setSavingVerificationOrderId(order.id);
                                            try {
                                              await api.saveMasterVerification(order.id, updatedVerification);
                                              fetchDashboardAndConfig();
                                            } catch (err) {
                                              alert("Failed to update verification check: " + err.message);
                                            } finally {
                                              setSavingVerificationOrderId(null);
                                            }
                                          }}
                                        />
                                        <span style={{ textDecoration: isChecked ? 'line-through' : 'none', color: isChecked ? 'var(--text-muted)' : 'var(--text-primary)' }}>
                                          {item.label}
                                        </span>
                                      </label>
                                    );
                                  })}
                                </div>
                              </div>
                            )}

                            {/* Submit Completion Section */}
                            {currentUser.role === 'Tailor' && (
                              <div style={{
                                marginTop: '12px',
                                padding: '16px',
                                background: 'rgba(15,41,30,0.02)',
                                border: '1px solid rgba(15,41,30,0.1)',
                                borderRadius: '8px',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '12px'
                              }}>
                                <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                                  Submit Stitching Completion & Photos
                                </h4>
                                
                                <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                  <div>
                                    <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Tailor Completion Comments</label>
                                    <textarea 
                                      className="form-control"
                                      style={{ height: '70px', fontSize: '13px' }}
                                      placeholder="Enter stitching details, alterations made, or fabric remarks..."
                                      id={`comments-${order.id}`}
                                      defaultValue={order.tailor_comments || ''}
                                    />
                                  </div>
                                  <div>
                                    <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Upload Completed Garment Photo</label>
                                    <input
                                      type="file"
                                      className="form-control"
                                      style={{ fontSize: '13px' }}
                                      id={`image-${order.id}`}
                                      accept="image/*"
                                    />
                                    <input
                                      type="file"
                                      style={{ display: 'none' }}
                                      id={`image-${order.id}-camera`}
                                      accept="image/*"
                                      capture="environment"
                                    />
                                    <label
                                      htmlFor={`image-${order.id}-camera`}
                                      className="btn-secondary"
                                      style={{ display: 'inline-block', fontSize: '12px', padding: '6px 10px', marginTop: '6px', cursor: 'pointer' }}
                                    >
                                      📷 Take photo
                                    </label>
                                    {order.completed_garment_image && (
                                      <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <span style={{ fontSize: '11px', color: '#107c41', fontWeight: 600 }}>✓ Picture Uploaded</span>
                                        <a href={order.completed_garment_image} target="_blank" rel="noreferrer" style={{ fontSize: '11px', color: 'var(--accent-text, #b07c40)', textDecoration: 'underline' }}>View Image</a>
                                      </div>
                                    )}
                                  </div>
                                </div>

                                <button
                                  className="btn-primary"
                                  style={{ alignSelf: 'flex-end', padding: '6px 16px', fontSize: '12px' }}
                                  disabled={submittingCompletionId === order.id}
                                  onClick={async () => {
                                    if (submittingCompletionId) return;
                                    const commentVal = document.getElementById(`comments-${order.id}`).value;
                                    const fileInput = document.getElementById(`image-${order.id}`);
                                    const cameraInput = document.getElementById(`image-${order.id}-camera`);
                                    const file = fileInput.files[0] || cameraInput?.files[0];

                                    setSubmittingCompletionId(order.id);
                                    try {
                                      await api.submitCompletion(order.id, commentVal, file);
                                      alert("Completion report submitted successfully!");
                                      fetchDashboardAndConfig();
                                    } catch (err) {
                                      alert("Submission failed: " + err.message);
                                    } finally {
                                      setSubmittingCompletionId(null);
                                    }
                                  }}
                                >
                                  {submittingCompletionId === order.id ? 'Submitting…' : 'Submit & Send for Quality Check'}
                                </button>
                              </div>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>

                {/* The tailor's alteration queue. A list of its own, not rows
                    smuggled into the order registry: an alteration is a
                    separate job against a delivered order. */}
                <div style={{ marginTop: '20px' }}>
                  <AlterationList
                    title="My Alterations"
                    params={{ assigned_to_me: '1', open: '1' }}
                    onOpenAlteration={openAlteration}
                  />
                </div>
              </>
            )}

            {dashboardTab === 'overview' && (
              <>
                <PageHeader
                  title={t('dashboard.welcomeBackUser', `Welcome back, ${currentUserName}! 👋`, { name: currentUserName })}
                  subtitle={t('dashboard.subtitle')}
                  meta={<HeaderClock />}
                  aside={(
                    <>
                      <button
                        type="button"
                        className="btn-secondary at-btn-sm"
                        disabled={markingNotificationsRead}
                        title={t('common.inboxAlerts', 'Inbox Alerts')}
                        aria-label={t('common.inboxAlerts', 'Inbox Alerts')}
                        onClick={() => {
                          setShowNotificationsDrawer(true);
                          if (markingNotificationsRead) return;
                          setMarkingNotificationsRead(true);
                          api.markNotificationsAsRead(currentUser.role || 'Owner', currentUser.email)
                            .then(() => fetchNotifications())
                            .catch(() => {})
                            .finally(() => setMarkingNotificationsRead(false));
                        }}
                        style={{ position: 'relative', borderRadius: '999px' }}
                      >
                        <Bell size={16} />
                        {notifications.filter(n => !n.is_read).length > 0 && (
                          <span style={{ backgroundColor: 'var(--danger-color)', color: '#fff', borderRadius: '10px',
                                         padding: '1px 7px', fontSize: '10px', fontWeight: 700 }}>
                            {notifications.filter(n => !n.is_read).length}
                          </span>
                        )}
                      </button>
                      <div className="user-profile-widget">
                        <div className="user-avatar-circle">
                          <UserAvatar user={currentUser} />
                        </div>
                        <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                      </div>
                    </>
                  )}
                  actions={(
                    <>
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={loading}
                        onClick={() => fetchDashboardAndConfig()}
                        style={{ padding: '10px 16px', fontSize: '13px' }}
                        title="Refresh Dashboard Data"
                      >
                        {!loading && <RotateCw size={15} />}
                        <span>{loading ? t('common.loading', 'Loading...') : t('common.refresh', 'Refresh')}</span>
                      </button>
                      <button className="btn-primary" style={{ padding: '10px 18px' }} onClick={() => setView('order-selector')}>
                        <Plus size={16} />
                        {t('dashboard.newOrder')}
                      </button>
                    </>
                  )}
                />

                {showOnboarding && (
                  <section className="content-card" style={{ padding: '20px', marginBottom: '16px', border: '1px solid var(--border-color)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '12px' }}>
                      <div>
                        <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: '20px', fontWeight: 500 }}>Getting started</h2>
                        <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                          {onboardingSteps.filter(step => step.done).length} of {onboardingSteps.length} done — this is the order the work flows in.
                        </p>
                      </div>
                      <button
                        type="button" className="btn-secondary" style={{ fontSize: '11px', padding: '4px 10px' }}
                        onClick={() => {
                          setOnboardingDismissed(true);
                          try {
                            localStorage.setItem(`onboarding_dismissed_${localStorage.getItem('tenant_id') || ''}`, '1');
                          } catch { /* per-device convenience only */ }
                        }}
                      >
                        Dismiss
                      </button>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      {onboardingSteps.map((step, i) => (
                        <button
                          key={step.key}
                          type="button"
                          disabled={step.done || !step.go}
                          onClick={step.go}
                          style={{
                            display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 10px',
                            background: 'transparent', border: 'none', borderRadius: '6px', textAlign: 'left',
                            cursor: step.done || !step.go ? 'default' : 'pointer', width: '100%',
                            color: step.done ? 'var(--text-muted)' : 'var(--text-primary)',
                          }}
                        >
                          <span style={{
                            width: '20px', height: '20px', borderRadius: '50%', flexShrink: 0,
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            border: step.done ? 'none' : '1.5px solid var(--border-color)',
                            background: step.done ? '#10b981' : 'transparent', color: '#fff', fontSize: '12px',
                          }}>
                            {step.done ? <Check size={12} /> : i + 1}
                          </span>
                          <span style={{ fontSize: '13px', textDecoration: step.done ? 'line-through' : 'none' }}>
                            {step.label}
                          </span>
                          {!step.done && step.go && <ArrowRight size={13} style={{ marginLeft: 'auto', opacity: 0.5 }} />}
                        </button>
                      ))}
                    </div>
                  </section>
                )}

                {/* The money reads first, then what needs acting on, then today,
                    then detail. All figures from /api/dashboard/ (dashboardData). */}
                {(() => {
                  const s = dashboardData?.stats || {};
                  const outstanding = Number(s.outstanding) || 0;
                  const overdue = Number(s.overdue) || 0;
                  return (
                    <section className="at-stat-grid" style={{ marginBottom: 'var(--space-5)' }}>
                      <StatCard icon={TrendingUp} tone="green" label="Revenue this month"
                                value={inr(s.revenue_month)} sub={`${inr(s.revenue_total)} all time`} />
                      <StatCard icon={Wallet} tone="amber" label="To collect" value={inr(outstanding)}
                                sub={outstanding > 0 ? 'across active orders' : 'all settled'}
                                onClick={() => setDashboardTab('orders')} />
                      <StatCard icon={ClipboardList} tone="violet" label="Active orders" value={s.active_orders ?? 0}
                                sub={`${s.due_soon ?? 0} due this week${overdue ? ` · ${overdue} overdue` : ''}`}
                                onClick={() => setDashboardTab('orders')} />
                      <StatCard icon={Users} tone="blue" label="Customers" value={s.total_customers ?? 0}
                                sub={`${s.total_orders ?? 0} orders total`}
                                onClick={() => setDashboardTab('customers')} />
                    </section>
                  );
                })()}

                {/* Production pipeline: one tile per customer-facing status,
                    in the order an order moves through them. */}
                {(() => {
                  const dist = dashboardData?.stats?.status_distribution || {};
                  const ORDER = ['Received', 'Confirmed', 'Stylist Review', 'Design & Creation',
                                 'Quality Check', 'Ready for Dispatch', 'Shipped', 'Delivered'];
                  const LOOK = {
                    'Received': ['amber', Clock], 'Confirmed': ['amber', CheckCircle2],
                    'Stylist Review': ['violet', PenTool], 'Design & Creation': ['rose', Scissors],
                    'Quality Check': ['blue', ShieldCheck], 'Ready for Dispatch': ['violet', PackageCheck],
                    'Shipped': ['neutral', Truck], 'Delivered': ['green', CheckCircle2],
                  };
                  const rank = (st) => (ORDER.indexOf(st) === -1 ? 99 : ORDER.indexOf(st));
                  const entries = Object.entries(dist).sort((a, b) => rank(a[0]) - rank(b[0]));
                  const jump = (st) => {
                    setOrdersFilterTab(st === 'Shipped' || st === 'Delivered' ? st : 'Active');
                    setDashboardTab('orders');
                  };
                  return (
                    <SectionCard icon={Boxes} tone="green" title="Production Pipeline"
                                 action={() => setDashboardTab('orders')} actionLabel="View All Orders"
                                 style={{ marginBottom: 'var(--space-5)' }}>
                      {entries.length === 0 ? (
                        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                          No orders yet. Create the first one to see it move through the floor.
                        </div>
                      ) : (
                        <div className="at-pipeline">
                          {entries.map(([st, count]) => {
                            const [tone, Icon] = LOOK[st] || ['neutral', Package];
                            return (
                              <button key={st} type="button" className={`at-pipeline-tile at-stat--${tone}`} onClick={() => jump(st)}>
                                <IconTile icon={Icon} tone={tone} size={34} iconSize={16} />
                                <span className="at-pipeline-value">{count}</span>
                                <span className="at-pipeline-label">{t(`status.${st}`, st)}</span>
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </SectionCard>
                  );
                })()}

                {/* Needs attention | Today */}
                <div className="at-grid-2" style={{ marginBottom: 'var(--space-5)' }}>
                  <SectionCard icon={AlertCircle} tone="rose" title="Needs Attention"
                               action={() => setDashboardTab('orders')} actionLabel="View All">
                    {(() => {
                      const att = dashboardData?.attention || {};
                      const due = att.due || [];
                      const unpaid = att.unpaid || [];
                      if (!due.length && !unpaid.length && !att.low_stock && !att.pending_designs) {
                        return <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                          Nothing needs you right now — no overdue orders, balances or low stock.
                        </div>;
                      }
                      const row = (key, onClick, ref, label, badge) => (
                        <div key={key} className="at-row at-row--tap" onClick={onClick}>
                          {ref && <span className="at-row-title" style={{ minWidth: '44px' }}>{ref}</span>}
                          <span className="at-row-main" style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>{label}</span>
                          {badge}
                          <ChevronRight size={16} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                        </div>
                      );
                      return (
                        <div>
                          {due.map((o) => row(`due-${o.id}`, () => setDashboardTab('orders'), orderRef(o), o.customer || 'Customer',
                            <span className={`ui-badge ui-badge--${o.overdue ? 'danger' : 'warning'}`}>
                              {o.overdue ? 'Overdue' : 'Due'} {o.due ? new Date(o.due).toLocaleDateString([], { day: 'numeric', month: 'short' }) : ''}
                            </span>))}
                          {unpaid.map((o) => row(`bal-${o.id}`, () => setDashboardTab('orders'), orderRef(o), o.customer || 'Customer',
                            <span className="ui-badge ui-badge--warning">{inr(o.balance)} due</span>))}
                          {att.low_stock > 0 && row('stock', () => setDashboardTab('inventory'), null, 'Low stock',
                            <span className="ui-badge ui-badge--warning">{att.low_stock} item{att.low_stock === 1 ? '' : 's'}</span>)}
                          {att.pending_designs > 0 && row('designs', () => setDashboardTab('designWork'), null, 'Designs awaiting review',
                            <span className="ui-badge ui-badge--info">{att.pending_designs}</span>)}
                        </div>
                      );
                    })()}
                  </SectionCard>

                  <SectionCard icon={CalendarDays} tone="green" title="Today">
                    {(() => {
                      const today = dashboardData?.today || {};
                      const appts = today.appointments || [];
                      return (
                        <>
                          <div style={{ display: 'flex', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
                            <button type="button" className="at-pipeline-tile at-stat--green" style={{ flex: 1 }}
                                    onClick={() => setDashboardTab('staff')}>
                              <span className="at-pipeline-value" style={{ color: 'var(--tone-green-fg)' }}>{today.staff_working ?? 0}</span>
                              <span className="at-pipeline-label">on the floor now</span>
                            </button>
                            <div className="at-pipeline-tile at-stat--neutral" style={{ flex: 1, cursor: 'default' }}>
                              <span className="at-pipeline-value">{today.staff_present ?? 0}</span>
                              <span className="at-pipeline-label">present today</span>
                            </div>
                          </div>
                          {appts.length === 0 ? (
                            <div style={{ textAlign: 'center', padding: 'var(--space-2) 0' }}>
                              <IconTile icon={Calendar} tone="neutral" size={40} iconSize={18} />
                              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', margin: 'var(--space-2) 0 var(--space-3)' }}>
                                No appointments booked for today.
                              </div>
                              <button type="button" className="btn-primary at-btn-sm" style={{ margin: '0 auto' }}
                                      onClick={() => { setEditingAppointment(null); setAppointmentForm(blankAppointmentForm); setShowAppointmentModal(true); }}>
                                <Plus size={14} /> {t('dashboard.bookAppointment', 'Book Appointment')}
                              </button>
                            </div>
                          ) : (
                            <div>
                              {appts.map((a) => (
                                <div key={a.id} className="at-row">
                                  <span className="at-row-main" style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>
                                    <b>{a.time}</b> · {a.customer || 'Customer'}</span>
                                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>{a.type}{a.with ? ` · ${a.with}` : ''}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </>
                      );
                    })()}
                  </SectionCard>
                </div>

                {/* Recent orders | Quick actions */}
                <div className="at-grid-2">
                  <SectionCard icon={ShoppingBag} tone="blue" title="Recent Orders"
                               action={() => setDashboardTab('orders')} actionLabel={t('dashboard.viewAll', 'View all')}>
                    {!dashboardData?.recent_orders || dashboardData.recent_orders.length === 0 ? (
                      <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
                        No orders yet.
                      </div>
                    ) : (
                      <div>
                        {dashboardData.recent_orders.map((order) => (
                          <div key={order.id || order.order_id} className="at-row at-row--tap"
                               onClick={() => setDashboardTab('orders')}>
                            <span className="at-row-title" style={{ minWidth: '44px' }}>{orderRef(order)}</span>
                            <span className="at-row-main">
                              <span className="at-row-title" style={{ fontWeight: 500 }}>{order.customer_name || order.customer || 'Customer'}</span>
                              <span className="at-row-sub">{order.garment_label || ''}</span>
                            </span>
                            <span style={{ textAlign: 'right' }}>
                              <div className="at-row-title at-num">{order.total_amount != null ? inr(order.total_amount) : ''}</div>
                              <div className="at-row-sub">{t(`status.${order.order_status}`, order.order_status || order.status || '')}</div>
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </SectionCard>

                  <SectionCard icon={Sparkles} tone="amber" title="Quick Actions">
                    <section className="quick-action-button-grid" style={{ marginBottom: 0 }}>
                      <div className="quick-action-item" onClick={() => setView('order-selector')}>
                        <div className="quick-action-icon-box"><ShoppingBag size={18} /></div>
                        <h4>{t('dashboard.newOrder')}</h4>
                      </div>
                      <div className="quick-action-item" onClick={() => setDashboardTab('staff')}>
                        <div className="quick-action-icon-box"><Scissors size={18} /></div>
                        <h4>{t('dashboard.manageStaff', 'Manage Staff')}</h4>
                      </div>
                      <div className="quick-action-item" onClick={() => setDashboardTab('designs')}>
                        <div className="quick-action-icon-box"><Heart size={18} /></div>
                        <h4>{t('dashboard.designCatalog', 'Design Catalog')}</h4>
                      </div>
                      <div className="quick-action-item" onClick={() => setDashboardTab('fabrics')}>
                        <div className="quick-action-icon-box"><Compass size={18} /></div>
                        <h4>{t('dashboard.fabricLibrary', 'Fabric Library')}</h4>
                      </div>
                      <div className="quick-action-item" onClick={() => { setEditingAppointment(null); setAppointmentForm(blankAppointmentForm); setShowAppointmentModal(true); }}>
                        <div className="quick-action-icon-box"><Calendar size={18} /></div>
                        <h4>{t('dashboard.bookAppointment', 'Book Appointment')}</h4>
                      </div>
                      <div className="quick-action-item" onClick={() => setDashboardTab('finance')}>
                        <div className="quick-action-icon-box"><Wallet size={18} /></div>
                        <h4>{t('dashboard.costPnl', 'Cost & P&L')}</h4>
                      </div>
                    </section>
                  </SectionCard>
                </div>
              </>
            )}

            {/* INVENTORY TAB */}
            {dashboardTab === 'inventory' && (
              <Suspense fallback={<ScreenLoading />}>
                <InventoryPanel currentUser={currentUser} />
              </Suspense>
            )}

            {dashboardTab === 'staff' && (
              <Suspense fallback={<ScreenLoading />}>
                <StaffPanel currentUser={currentUser} />
              </Suspense>
            )}

            {dashboardTab === 'finance' && (
              <Suspense fallback={<ScreenLoading />}>
                <FinancePanel />
              </Suspense>
            )}

            {/* Post-delivery alterations. Its own screen, deliberately not a
                second copy of the order registry: an alteration is a separate
                job that merely points at the order it came from. */}
            {dashboardTab === 'alterations' && (
              <Suspense fallback={<ScreenLoading />}>
                <AlterationsPanel
                  currentUser={currentUser}
                  initialAlterationId={openAlterationId}
                  onBackToList={() => setOpenAlterationId(null)}
                  key={openAlterationId || 'list'}
                />
              </Suspense>
            )}

            {/* 2. MANAGE FABRICS TAB */}
            {dashboardTab === 'fabrics' && (() => {
              const q = fabricQuery;
              const materials = [...new Set(fabrics.map(f => f.material).filter(Boolean))].sort();
              const colours = [...new Set(fabrics.map(f => f.color).filter(Boolean))].sort();
              const filtered = fabrics.filter(f => {
                if (q.material !== 'All' && f.material !== q.material) return false;
                if (q.colour !== 'All' && f.color !== q.colour) return false;
                if (q.availability === 'Available' && !f.is_available) return false;
                if (q.availability === 'Out of Stock' && f.is_available) return false;
                if (q.search.trim()) {
                  const needle = q.search.toLowerCase();
                  return [f.name, f.material, f.color].some(v => (v || '').toLowerCase().includes(needle));
                }
                return true;
              }).sort((a, b) => (
                q.sort === 'name' ? String(a.name).localeCompare(String(b.name))
                  : q.sort === 'price_asc' ? Number(a.price_per_meter) - Number(b.price_per_meter)
                  : q.sort === 'price_desc' ? Number(b.price_per_meter) - Number(a.price_per_meter)
                  : (b.id || 0) - (a.id || 0)));
              const available = fabrics.filter(f => f.is_available).length;
              const avg = fabrics.length
                ? fabrics.reduce((sum, f) => sum + Number(f.price_per_meter || 0), 0) / fabrics.length : 0;
              const openNew = () => {
                setEditingFabric(null);
                setFabricGroups([blankGroup()]);
                setShowFabricModal(true);
              };
              const openEdit = (fabric) => {
                setEditingFabric(fabric);
                setFabricGroups([{
                  ...blankGroup(),
                  kind: fabric.kind || '',
                  variant: fabric.variant || '',
                  placements: (fabric.placements || []).map(
                    ({ garment, section, slot }) => ({ garment, section, slot })),
                  materials: [{
                    ...blankMaterial(),
                    name: fabric.name,
                    material: fabric.material,
                    color: fabric.color,
                    color_hex: fabric.color_hex || '#c8a97e',
                    price_per_meter: String(fabric.price_per_meter),
                    image_url: fabric.image_url || '',
                    image_urls: fabric.image_urls || [],
                    is_available: fabric.is_available,
                  }],
                }]);
                setShowFabricModal(true);
              };
              const pick = (key, label, options) => (
                <label className="at-field" style={{ minWidth: '140px' }}>
                  <span className="at-field-hint" style={{ fontWeight: 600 }}>{label}</span>
                  <div className="at-field-control" style={{ minHeight: '42px' }}>
                    <select className="form-control" value={q[key]} onChange={(e) => setFabricQuery({ ...q, [key]: e.target.value })}>
                      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </div>
                </label>
              );
              return (
              <>
                <PageHeader
                  title={t('fabricsPage.title')}
                  subtitle={t('fabricsPage.subtitle')}
                  aside={(
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <UserAvatar user={currentUser} />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  )}
                  actions={(
                    <button className="btn-primary" style={{ padding: '10px 18px' }} onClick={openNew}>
                      <Plus size={16} />
                      {t('fabricsPage.addNewFabric')}
                    </button>
                  )}
                />

                <div className="at-toolbar" style={{ marginTop: 0, alignItems: 'flex-end' }}>
                  <SearchBox value={q.search} onChange={(v) => setFabricQuery({ ...q, search: v })}
                             placeholder="Search fabrics by name, material, colour…" />
                  <div className="at-toolbar-right" style={{ alignItems: 'flex-end' }}>
                    {pick('material', 'Material', [['All', 'All'], ...materials.map(m => [m, m])])}
                    {pick('colour', 'Colour', [['All', 'All'], ...colours.map(c => [c, c])])}
                    {pick('availability', 'Availability', [['All', 'All'], ['Available', 'Available'], ['Out of Stock', 'Out of Stock']])}
                    {pick('sort', 'Sort by', [['newest', 'Newest First'], ['name', 'Name A–Z'], ['price_asc', 'Price: low to high'], ['price_desc', 'Price: high to low']])}
                  </div>
                </div>

                <section className="at-stat-grid" style={{ marginBottom: 'var(--space-5)' }}>
                  <StatCard icon={Layers} tone="amber" label="Total Fabrics" value={fabrics.length} />
                  <StatCard icon={CheckCircle2} tone="green" label="Available" value={available} />
                  <StatCard icon={Package} tone="rose" label="Out of Stock" value={fabrics.length - available} />
                  <StatCard icon={Tag} tone="amber" label="Average Price / mtr" value={formatMoney(avg)} />
                </section>

                {fabrics.length === 0 ? (
                  <div className="ui-card" style={{ padding: '48px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                    <div style={{ fontWeight: 'var(--weight-semibold)', color: 'var(--text-primary)', marginBottom: '6px' }}>
                      {t('fabricsPage.noFabricsYet', 'No fabrics in your library yet')}
                    </div>
                    <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', maxWidth: '44ch', margin: '0 auto 16px', lineHeight: 'var(--leading-normal)' }}>
                      {t('fabricsPage.noFabricsHint', 'Add the cloths you keep in stock — their colour, material and price per metre — so they can be picked when you take an order.')}
                    </div>
                    <button className="btn-primary" style={{ margin: '0 auto' }} onClick={openNew}><Plus size={16} /> {t('fabricsPage.addNewFabric')}</button>
                  </div>
                ) : (
                  <div className="at-fabric-grid">
                    {filtered.length === 0 && (
                      <div className="ui-card" style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-muted)', gridColumn: '1 / -1' }}>
                        No fabrics match these filters.
                      </div>
                    )}
                    {filtered.map(fabric => (
                      <article key={fabric.id} className="ui-card at-fabric">
                        {/* "Aqua Blue" is not a CSS colour, so the tile fell back
                            to grey for every fabric named the way a boutique
                            names one. The swatch the owner picked is exact; the
                            name map is the honest second choice. */}
                        <div className="at-fabric-media" style={{ background: fabric.color_hex || getColorCircleStyle(fabric.color) }}>
                          {fabric.image_url
                            ? <img src={resolveMediaUrl(fabric.image_url)} alt={fabric.name} />
                            : <span className="at-fabric-swatch-name">{fabric.color}</span>}
                          <span className={`ui-badge at-fabric-pill ${fabric.is_available ? 'ui-badge--success' : 'ui-badge--neutral'}`}>
                            ● {fabric.is_available ? 'Available' : 'Out of Stock'}
                          </span>
                        </div>
                        <div className="at-fabric-body">
                          <h4 className="at-fabric-name">{fabric.name}</h4>
                          <div className="at-fabric-meta">
                            <span><Layers size={13} /> Material: {fabric.material}</span>
                            <span className="at-fabric-price">{formatMoney(fabric.price_per_meter)}/mtr</span>
                            <span>
                              <Palette size={13} /> Colour: {fabric.color}
                              {fabric.color_hex && (
                                <i title={fabric.color_hex} style={{ width: '12px', height: '12px', borderRadius: '3px', background: fabric.color_hex, border: '1px solid var(--border-color)', display: 'inline-block' }} />
                              )}
                            </span>
                          </div>
                          {(fabric.kind_label || (fabric.placements || []).length > 0) && (
                            <div className="at-fabric-meta" style={{ gap: '6px', flexWrap: 'wrap' }}>
                              {fabric.kind_label && (
                                <span className="ui-badge">
                                  {fabric.variant_label || fabric.kind_label}
                                </span>
                              )}
                              {(fabric.placements || []).map((p) => (
                                <span key={p.id} className="ui-badge">{p.path}</span>
                              ))}
                            </div>
                          )}
                          <div className="at-fabric-actions">
                            <button className="btn-secondary at-btn-sm" onClick={() => openEdit(fabric)}>
                              <Edit2 size={12} /> Edit
                            </button>
                            <button className="btn-secondary at-btn-sm at-btn-danger" disabled={deletingFabricId === fabric.id} onClick={() => handleDeleteFabric(fabric.id)}>
                              {deletingFabricId === fabric.id ? 'Deleting…' : <><Trash2 size={12} /> Delete</>}
                            </button>
                          </div>
                        </div>
                      </article>
                    ))}
                    <button type="button" className="at-fabric--add" onClick={openNew}>
                      <span className="at-photo-plus" style={{ width: 56, height: 56 }}><Plus size={22} /></span>
                      <span className="at-section-title">Add New Fabric</span>
                      <span className="at-section-sub">Expand your collection with new fabrics.</span>
                      <span className="btn-primary" style={{ marginTop: '8px' }}><Plus size={16} /> Add Fabric</span>
                    </button>
                  </div>
                )}
              </>
              );
            })()}

            {/* 3. MANAGE TAILORS TAB */}

            {/* 4b. DESIGN WORK TAB -- assign, submit, review. One component for
                 both ends of the loop; see features/designStudio/DesignWork. */}
            {dashboardTab === 'designWork' && (
              <>
                <PageHeader
                  icon={PenTool} tone="neutral"
                  title={t('designWorkPage.title', 'Design Work')}
                  subtitle={currentUser?.role === 'Designer'
                    ? t('designWorkPage.subtitleDesigner', 'The garments you have been asked to design.')
                    : t('designWorkPage.subtitleSupervisor', 'Assign a garment to a designer, and review what comes back.')}
                />
                <div className="portal-content">
                  <Suspense fallback={<ScreenLoading />}>
                    <DesignWork currentUser={currentUser} />
                  </Suspense>
                </div>
              </>
            )}

            {/* 4. MANAGE DESIGNS TAB */}
            {dashboardTab === 'designs' && (
              <>
                <PageHeader
                  title={t('designsPage.title')}
                  subtitle={t('designsPage.subtitle')}
                  aside={(
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <UserAvatar user={currentUser} />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  )}
                  actions={(!currentUser?.role || currentUser.role === 'Owner') && (
                      <button className="btn-primary" style={{ padding: '10px 18px' }} onClick={() => {
                        setEditingDesign(null);
                        setDesignForm({
                          name: '',
                          garment_type: 'Lehenga',
                          neckline_style: '',
                          sleeve_style: '',
                          image_url: '',
                          is_boutique: true,
                          price: 0,
                          description: ''
                        });
                        setShowDesignModal(true);
                      }}>
                        <Plus size={16} />
                        {t('designsPage.addNewDesign')}
                      </button>
                  )}
                />

                <div className="design-manager-content">
                  {/* Dashboard first: stats before images, so opening the module
                      answers "how is the library doing" rather than dropping
                      straight into a grid. */}
                  <div className="tabs-header" style={{ marginBottom: '16px' }}>
                    <button className={`tab-btn ${designsView === 'dashboard' ? 'active' : ''}`}
                            onClick={() => setDesignsView('dashboard')}>
                      Dashboard
                    </button>
                    <button className={`tab-btn ${designsView === 'library' ? 'active' : ''}`}
                            onClick={() => setDesignsView('library')}>
                      Boutique Designs
                    </button>
                  </div>

                  <Suspense fallback={<div className="content-card">Loading…</div>}>
                    {designsView === 'dashboard' ? (
                      <DesignDashboard
                        onOpenLibrary={() => setDesignsView('library')}
                        canManageDesigners={!currentUser?.role || currentUser.role === 'Owner'}
                      />
                    ) : (
                      <DesignLibrary
                        refreshToken={designLibraryToken}
                        canReview={!currentUser?.role || currentUser.role === 'Owner'}
                        onUploaded={() => setDesignsView('library')}
                        onEditDesign={(design) => {
                          setEditingDesign({ id: design.id });
                          setDesignForm({
                            name: design.title || '',
                            garment_type: design.garment_type || 'Lehenga',
                            neckline_style: (design.attributes || {}).neckline_style || '',
                            sleeve_style: (design.attributes || {}).sleeve_style || '',
                            image_url: design.image_url || '',
                            is_boutique: design.source === 'catalogue',
                            price: String(design.estimated_price ?? 0),
                            description: design.description || '',
                            catalogue: design.catalogue?.category ? {
                              category: design.catalogue.category,
                              subcategory: design.catalogue.subcategory || undefined,
                              option: design.catalogue.option || undefined,
                            } : {},
                            catalogue_path: design.catalogue?.category ? {
                              category: design.catalogue.category,
                              subcategory: design.catalogue.subcategory || '',
                              option: design.catalogue.option || '',
                            } : null,
                          });
                          setShowDesignModal(true);
                        }}
                        onDeleteDesign={(design) => handleDeleteDesign(design.id)}
                      />
                    )}
                  </Suspense>
                </div>
              </>
            )}

            {/* Manage Orders Tab */}
            {dashboardTab === 'orders' && (
              <>
                <PageHeader
                  title={t('ordersPage.title')}
                  subtitle={t('ordersPage.subtitle')}
                  aside={<SearchBox value={ordersSearch} onChange={setOrdersSearch} placeholder={t('ordersPage.searchPlaceholder')} />}
                  actions={(!currentUser?.role || currentUser.role === 'Owner') && (
                    <button className="btn-primary" style={{ padding: '10px 18px' }} onClick={handleStartNewCustomer}>
                      <Plus size={16} /> {t('ordersPage.newOrder')}
                    </button>
                  )}
                />

                {(() => {
                  const total = ordersList.length;
                  const shipped = ordersList.filter(o => o.order_status === 'Shipped').length;
                  const delivered = ordersList.filter(o => o.order_status === 'Delivered').length;
                  const active = total - shipped - delivered;
                  return (
                    <>
                      <section className="at-stat-grid">
                        <StatCard icon={ShoppingCart} tone="green" label="Total Orders" value={total} sub="all time"
                                  onClick={() => setOrdersFilterTab('All')} />
                        <StatCard icon={Clock} tone="amber" label="Active Orders" value={active} sub="in progress"
                                  onClick={() => setOrdersFilterTab('Active')} />
                        <StatCard icon={Truck} tone="blue" label="Shipped" value={shipped} sub="on their way"
                                  onClick={() => setOrdersFilterTab('Shipped')} />
                        <StatCard icon={CheckCircle2} tone="green" label="Delivered" value={delivered} sub="handed over"
                                  onClick={() => setOrdersFilterTab('Delivered')} />
                      </section>
                      <div className="at-toolbar">
                        <Chips value={ordersFilterTab} onChange={setOrdersFilterTab} options={[
                          { key: 'All', label: t('ordersPage.filterAll'), count: total },
                          { key: 'Active', label: t('ordersPage.filterActive'), count: active },
                          { key: 'Shipped', label: t('ordersPage.filterShipped'), count: shipped },
                          { key: 'Delivered', label: t('ordersPage.filterDelivered'), count: delivered },
                        ]} />
                        <div className="at-toolbar-right">
                          {/* List / Board: two drawings of the same filtered orders. */}
                          <Segmented ariaLabel="Orders view" value={ordersView} onChange={setOrdersView} options={[
                            { key: 'kanban', label: 'Board', icon: LayoutGrid },
                            { key: 'list', label: 'List', icon: List },
                          ]} />
                        </div>
                      </div>
                    </>
                  );
                })()}

                <div className="orders-registry-content" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                  {ordersView === 'kanban' ? (
                    <OrderKanban
                      orders={ordersList.filter(orderMatchesFilters)}
                      workflow={boutiqueSettings?.workflow_config}
                      onOpen={(order, stage) => openStageReview(order, stage)}
                      onChanged={fetchDashboardAndConfig}
                    />
                  ) : (
                  /* Orders list */
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                    {(() => {
                      const statusTone = (st) =>
                        st === 'Delivered' ? 'success'
                          : st === 'Cancelled' ? 'neutral'
                          : (st === 'Shipped' || st === 'Ready for Dispatch') ? 'info'
                          : 'warning';
                      const filtered = ordersList.filter(orderMatchesFilters);

                      if (filtered.length === 0) {
                        return (
                          <div className="ui-card" style={{ padding: 'var(--space-10)', textAlign: 'center', color: 'var(--text-muted)' }}>
                            {ordersList.length === 0 ? (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', alignItems: 'center' }}>
                                <div style={{ fontWeight: 'var(--weight-semibold)', color: 'var(--text-primary)', fontSize: 'var(--text-md)' }}>{t('ordersPage.noOrdersYet', 'No orders yet')}</div>
                                <div style={{ fontSize: 'var(--text-sm)', maxWidth: '44ch', lineHeight: 'var(--leading-normal)' }}>
                                  {t('ordersPage.noOrdersYetDesc', 'Orders you create will appear here, with their production stage and who is working on them.')}
                                </div>
                                <button className="btn-primary" onClick={() => setView('order-selector')}>
                                  {t('ordersPage.createFirstOrder', 'Create your first order')}
                                </button>
                              </div>
                            ) : t('ordersPage.noOrdersMatching', 'No orders found matching the criteria.')}
                          </div>
                        );
                      }

                      return filtered.map(order => (
                        <div key={order.id} className="ui-card" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', padding: 'var(--space-6)' }}>
                          {/* Header: id + status read first; client/date meta; verification note */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                                <span style={{ fontWeight: 'var(--weight-bold)', fontSize: 'var(--text-lg)', color: 'var(--text-primary)', fontFamily: 'var(--font-serif)' }}>{orderRef(order)}</span>
                                <span className={`ui-badge ui-badge--${statusTone(order.order_status)}`}>
                                  {order.order_status_display || t(`status.${order.order_status}`, order.order_status)}
                                </span>
                              </div>
                              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginTop: 'var(--space-1)' }}>
                                {t('ordersPage.client', 'Client:')} <strong style={{ color: 'var(--text-primary)' }}>{order.customer_name}</strong>
                                {'  ·  '}{t('ordersPage.created', 'Created:')} {fmtDate(order.order_date)}
                              </div>
                              {(() => {
                                const v = order.master_verification || {};
                                const total = 6 + (orderGarmentNames(order).includes('Saree') ? 1 : 0);
                                const checked = Object.values(v).filter(Boolean).length;
                                if (checked > 0) {
                                  return (
                                    <span className="ui-badge ui-badge--success" style={{ marginTop: 'var(--space-2)' }}>
                                      👑 {t('ordersPage.masterVerified', 'Master Verified:')} {checked}/{total} ({Math.round((checked/total)*100)}%)
                                    </span>
                                  );
                                }
                                return null;
                              })()}
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                              <span className="ui-eyebrow">{t('ordersPage.updateStatus', 'Update status')}</span>
                              <select
                                className="form-control"
                                style={{ fontSize: 'var(--text-sm)', padding: '6px 12px', width: '180px', margin: 0 }}
                                value={order.order_status}
                                disabled={updatingStatusOrderId === order.id}
                                onChange={(e) => {
                                  if (updatingStatusOrderId) return;
                                  setUpdatingStatusOrderId(order.id);
                                  api.updateOrderStatus(order.id, e.target.value)
                                    .then(() => fetchDashboardAndConfig())
                                    .catch(err => alert("Failed to update status: " + err.message))
                                    .finally(() => setUpdatingStatusOrderId(null));
                                }}
                              >
                                {['Received', 'Confirmed', 'Stylist Review', 'Design & Creation', 'Quality Check', 'Ready for Dispatch', 'Shipped', 'Delivered'].map(status => (
                                  <option key={status} value={status}>{t(`status.${status}`, status)}</option>
                                ))}
                              </select>
                            </div>
                          </div>

                          {/* Key facts strip: the four numbers/people to scan */}
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                               gap: 'var(--space-4)', padding: 'var(--space-4)', background: 'var(--surface-2)',
                               borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
                            <div>
                              <div className="ui-eyebrow">{t('ordersPage.supervisingMaster', 'Supervising Master')}</div>
                              <div style={{ fontSize: 'var(--text-base)', fontWeight: 'var(--weight-semibold)', marginTop: '2px', color: order.master_name ? 'var(--accent-text)' : 'var(--text-muted)' }}>{order.master_name || t('ordersPage.unassigned', 'Unassigned')}</div>
                            </div>
                            <div>
                              <div className="ui-eyebrow">{t('ordersPage.stitchingTailor', 'Stitching Tailor')}</div>
                              <div style={{ fontSize: 'var(--text-base)', fontWeight: 'var(--weight-semibold)', marginTop: '2px', color: order.tailor_name ? 'var(--text-primary)' : 'var(--text-muted)' }}>{order.tailor_name || t('ordersPage.unassigned', 'Unassigned')}</div>
                            </div>
                            {!isProductionStaff(currentUser.role) && (
                              <div>
                                <div className="ui-eyebrow">{t('ordersPage.totalValue', 'Total Value')}</div>
                                <div className="ui-stat-value" style={{ fontSize: 'var(--text-lg)', marginTop: '2px' }}>{inr(order.total_amount)}</div>
                              </div>
                            )}
                            <div>
                              <div className="ui-eyebrow">{t('ordersPage.estDelivery', 'Est. Delivery')}</div>
                              <div style={{ fontSize: 'var(--text-base)', fontWeight: 'var(--weight-semibold)', marginTop: '2px', color: 'var(--text-primary)' }}>{order.estimated_delivery ? fmtDate(order.estimated_delivery) : t('ordersPage.tbd', 'TBD')}</div>
                            </div>
                          </div>

                          {/* Production timeline */}
                          <StageTimeline
                            stages={order.stages}
                            onSelectStage={(stage) => openStageReview(order, stage)}
                          />

                          <GarmentGallery order={order} onChanged={fetchDashboardAndConfig} />

                          <CustomerMessageQueue
                            orderId={order.id}
                            messages={queuedMessages.filter(m => m.order === order.id)}
                            onMarkSent={handleMarkMessageSent}
                          />

                          {/* Raw materials checklist */}
                          <div style={{ padding: 'var(--space-4)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', textAlign: 'left' }}>
                            <div className="ui-eyebrow" style={{ marginBottom: 'var(--space-2)' }}>🧵 Raw materials checklist</div>
                            <MaterialsChecklist orderId={order.id} role={currentUser.role} />
                          </div>

                          {/* Post-delivery alterations. Shown only once the
                              order is Delivered -- before that a fitting
                              problem is production's to fix, not a new job. */}
                          <OrderAlterations
                            order={order}
                            customerId={order.customer}
                            currentUser={currentUser}
                            onOpenAlteration={openAlteration}
                          />

                          {/* Master verification checklist */}
                          {currentUser.role === 'Master' && (
                            <div style={{ padding: 'var(--space-4)', background: 'var(--accent-color)',
                                 border: '1px solid var(--accent-border)', borderRadius: 'var(--radius-md)', textAlign: 'left' }}>
                              <div className="ui-eyebrow" style={{ marginBottom: 'var(--space-3)', color: 'var(--accent-text)' }}>👑 Master production verification</div>
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-2) var(--space-4)' }}>
                                {[
                                  { key: 'dress_cutting', label: 'Dress & Pattern Cutting' },
                                  { key: 'thread', label: 'Matching Thread & Accents' },
                                  { key: 'hemming', label: 'Hemming & Seam Finishes' },
                                  ...(order.customer_garment_type === 'Saree' ? [{ key: 'fall_pico', label: 'Fall & Pico / Peack' }] : []),
                                  { key: 'hook_buttons', label: 'Hook or Buttons Closure' },
                                  { key: 'pressing', label: 'Garment Steam Pressing' },
                                  { key: 'dispatch_trial', label: 'Dispatch or Fit Trial Ready' }
                                ].map(item => {
                                  const isChecked = order.master_verification?.[item.key] || false;
                                  return (
                                    <label key={item.key} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: 'var(--text-sm)', cursor: 'pointer' }}>
                                      <input
                                        type="checkbox"
                                        checked={isChecked}
                                        disabled={savingVerificationOrderId === order.id}
                                        onChange={async (e) => {
                                          if (savingVerificationOrderId) return;
                                          const updatedVerification = { ...(order.master_verification || {}), [item.key]: e.target.checked };
                                          setSavingVerificationOrderId(order.id);
                                          try {
                                            await api.saveMasterVerification(order.id, updatedVerification);
                                            fetchDashboardAndConfig();
                                          } catch (err) {
                                            alert("Failed to update verification check: " + err.message);
                                          } finally {
                                            setSavingVerificationOrderId(null);
                                          }
                                        }}
                                      />
                                      <span style={{ textDecoration: isChecked ? 'line-through' : 'none', color: isChecked ? 'var(--text-muted)' : 'var(--text-primary)' }}>
                                        {item.label}
                                      </span>
                                    </label>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* Delivery */}
                          <div style={{ background: 'var(--surface-2)', border: '1px dashed var(--border-strong)',
                               borderRadius: 'var(--radius-md)', padding: 'var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--weight-semibold)', color: 'var(--text-primary)' }}>
                              {t('ordersPage.deliveryMethodLabel', 'Delivery Method:')} {order.delivery_method_display || t(`deliveryMethod.${order.delivery_method}`, order.delivery_method)}
                            </div>
                            {order.delivery_method === 'Courier' && (
                              <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                                <div><strong>Courier Service Provider:</strong> {order.courier_service || 'TBD'}</div>
                                <div><strong>Tracking Reference:</strong> {order.tracking_number || 'TBD'}</div>
                                <div style={{ gridColumn: 'span 2', marginTop: '4px' }}>
                                  <strong>Shipping Address:</strong> {order.delivery_address || 'No address specified'}
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Tailor completion report */}
                          {(order.tailor_comments || order.completed_garment_image) && (
                            <div style={{ background: 'var(--accent-color)', border: '1px solid var(--accent-border)',
                                 borderRadius: 'var(--radius-md)', padding: 'var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                              <div className="ui-eyebrow" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', color: 'var(--accent-text)' }}>
                                <Scissors size={13} /> Stitching completion report
                              </div>
                              {order.tailor_comments && (
                                <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', margin: 0, fontStyle: 'italic' }}>
                                  "{order.tailor_comments}"
                                </p>
                              )}
                              {order.completed_garment_image && (
                                <div style={{ marginTop: '4px' }}>
                                  <span className="ui-eyebrow" style={{ display: 'block', marginBottom: '6px' }}>Garment photo</span>
                                  <a href={order.completed_garment_image} target="_blank" rel="noreferrer">
                                    <img src={order.completed_garment_image} alt="Completed Garment"
                                      style={{ width: '100px', height: '100px', objectFit: 'cover', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', cursor: 'pointer' }} />
                                  </a>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ));
                    })()}
                  </div>
                  )}
                </div>
              </>
            )}

            {/* 5. CUSTOMERS TAB */}
            {dashboardTab === 'customers' && !selectedDirectoryCustomer && (
              <>
                <PageHeader
                  title={t('customersPage.title')}
                  subtitle={t('customersPage.subtitle')}
                  aside={(
                    <>
                      <SearchBox value={searchQuery} onChange={setSearchQuery} placeholder={t('customersPage.searchPlaceholder')} />
                      <div className="user-profile-widget">
                        <div className="user-avatar-circle">
                          <UserAvatar user={currentUser} />
                        </div>
                        <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                      </div>
                    </>
                  )}
                  actions={(!currentUser?.role || currentUser.role === 'Owner') && (
                    <button className="btn-primary" style={{ padding: '10px 18px' }} onClick={handleStartNewCustomer}>
                      <Plus size={16} /> Add Customer
                    </button>
                  )}
                />

                {(() => {
                  const now = new Date();
                  const thisMonth = customersList.filter(c => {
                    const d = new Date(c.created_at);
                    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
                  }).length;
                  const vip = customersList.filter(c => c.segment === 'VIP').length;
                  const withOrders = customersList.filter(c => (c.order_count ?? c.orders?.length ?? 0) > 0).length;
                  const typeCount = (type) => type === 'All'
                    ? customersList.length
                    : customersList.filter(c => (c.customer_type || '').toLowerCase() === type.toLowerCase()).length;
                  return (
                    <>
                      <section className="at-stat-grid">
                        <StatCard icon={Users} tone="green" label="Total Customers" value={customersList.length}
                                  sub={`${withOrders} have ordered`} />
                        <StatCard icon={Crown} tone="amber" label="VIP Customers" value={vip} sub="by spend and orders" />
                        <StatCard icon={CalendarDays} tone="violet" label="New This Month" value={thisMonth} sub="registered" />
                        <StatCard icon={ShoppingBag} tone="blue" label="With Orders" value={withOrders} sub="at least one order" />
                      </section>
                      <div className="at-toolbar">
                        <Chips value={customerTypeFilter} onChange={setCustomerTypeFilter} options={[
                          { key: 'All', label: t('customersPage.filterAll'), count: typeCount('All') },
                          { key: 'Women', label: t('customersPage.filterWomen'), count: typeCount('Women') },
                          { key: 'Men', label: t('customersPage.filterMen'), count: typeCount('Men') },
                          { key: 'Kids', label: t('customersPage.filterKids'), count: typeCount('Kids') },
                        ]} />
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                          Showing {directoryCustomers.length} of {customersList.length}
                        </span>
                      </div>
                    </>
                  );
                })()}

                <div className="customers-list-container at-stack">
                  {loading && customersList.length === 0 ? (
                    <div className="ui-card" style={{ padding: '48px', textAlign: 'center' }}>
                      <span style={{ color: 'var(--text-muted)' }}>{t('common.loading')}</span>
                    </div>
                  ) : loadErrors.includes('customers') ? (
                    <div style={{ padding: '48px', textAlign: 'center', background: 'var(--danger-bg)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--danger-color)' }}>
                      <div style={{ color: 'var(--danger-color)', marginBottom: '12px' }}>Could not load the customer directory.</div>
                      <button type="button" className="btn-secondary" onClick={() => fetchDashboardAndConfig()}>Retry</button>
                    </div>
                  ) : directoryCustomers.length === 0 ? (
                    <div className="ui-card" style={{ padding: '48px', textAlign: 'center' }}>
                      {customersList.length === 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center' }}>
                          <div style={{ fontWeight: 'var(--weight-semibold)', color: 'var(--text-primary)' }}>{t('customersPage.noCustomersYet')}</div>
                          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', maxWidth: '44ch', lineHeight: 'var(--leading-normal)' }}>
                            Everyone you take an order for is kept here, with their measurements, past orders and preferences.
                          </div>
                          <button className="btn-primary" onClick={handleStartNewCustomer}>
                            {t('customersPage.addFirstCustomer')}
                          </button>
                        </div>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>{t('customersPage.noMatchingCustomers')}</span>
                      )}
                    </div>
                  ) : (
                    directoryCustomers.map(cust => {
                      const m = cust.measurements;
                      const parts = m?.additional_measurements?.stitch_parts || [];
                      const visible = m ? getVisibleMeasurementFields(parts) : [];
                      const FIELDS = [['bust', 'Bust'], ['waist', 'Waist'], ['hips', 'Hips'], ['shoulder', 'Shoulder'],
                                      ['arm_length', 'Arm'], ['neck', 'Neck'], ['length', 'Length']];
                      const shown = FIELDS.filter(([k]) => visible.includes(k)).slice(0, 4);
                      const tags = [
                        `${cust.garment_type || ''}${parts.length ? ` (${parts.join(', ')})` : ''}`.trim(),
                        cust.neckline_style && `Neck: ${cust.neckline_style}`,
                        cust.sleeve_style && `Sleeve: ${cust.sleeve_style}`,
                        cust.silhouette && `Silhouette: ${cust.silhouette}`,
                        cust.occasion && `${t('customersPage.occasion')} ${cust.occasion}`,
                      ].filter(Boolean);
                      const open = () => openDirectoryCustomer(cust);
                      const orders = cust.order_count ?? cust.orders?.length ?? 0;
                      return (
                        <div key={cust.id} className="ui-card" style={{ padding: 0 }}>
                          <div
                            className="at-customer"
                            role="button"
                            tabIndex={0}
                            onClick={open}
                            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } }}
                          >
                            <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', minWidth: 0 }}>
                              <AvatarInitials name={`${cust.first_name} ${cust.last_name}`} size={48} />
                              <div style={{ minWidth: 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                  <span style={{ fontFamily: 'var(--font-serif)', fontSize: 'var(--text-md)', fontWeight: 600, color: 'var(--text-primary)' }}>
                                    {cust.first_name} {cust.last_name}
                                  </span>
                                  <SegmentBadge segment={cust.segment} />
                                </div>
                                <div className="ui-eyebrow" style={{ color: 'var(--accent-text)', marginTop: '2px' }}>{cust.customer_type}</div>
                                <div className="at-contact">
                                  <span><Phone size={12} /> {formatMobile(cust.mobile_number)}</span>
                                  {cust.email_address && <span><Mail size={12} /> {cust.email_address}</span>}
                                  {(cust.city_region || cust.address) && <span><MapPin size={12} /> {cust.city_region || cust.address}</span>}
                                </div>
                              </div>
                            </div>

                            <div className="at-customer-cell">
                              <div className="ui-eyebrow">{t('customersPage.bodyMeasurements')}</div>
                              {m && shown.length > 0 ? (
                                <div className="at-measure-grid">
                                  {shown.map(([k, label]) => (
                                    <div key={k}>
                                      <div className="at-measure-label">{label}</div>
                                      <div className="at-measure-value">{m[k] || '—'}</div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>No size measurements logged yet.</span>
                              )}
                            </div>

                            <div className="at-customer-cell">
                              <div className="ui-eyebrow">{t('customersPage.bespokeProfile')}</div>
                              <div className="at-tags">
                                {tags.map(tag => <span key={tag} className="at-tag">{tag}</span>)}
                              </div>
                              {cust.custom_requirements && (
                                <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-muted)', marginTop: '6px', lineHeight: 1.4 }}>
                                  {cust.custom_requirements}
                                </div>
                              )}
                            </div>

                            <div className="at-customer-cell">
                              <div className="ui-eyebrow">Orders</div>
                              <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-primary)' }}>{orders}</div>
                              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                                {inr(cust.total_spend)} spent · {t('customersPage.registered')} {fmtDate(cust.created_at)}
                              </div>
                              <button
                                type="button"
                                className="at-link"
                                style={{ marginTop: '6px', fontSize: 'var(--text-xs)', color: 'var(--accent-text)' }}
                                onClick={(e) => { e.stopPropagation(); setExpandedDna(prev => ({ ...prev, [cust.id]: !prev[cust.id] })); }}
                              >
                                <Sparkles size={12} /> {expandedDna[cust.id] ? t('common.cancel') : t('customersPage.viewStyleDna')}
                              </button>
                            </div>

                            <ChevronRight className="at-customer-chevron" size={18} style={{ color: 'var(--text-muted)' }} />
                          </div>

                          {expandedDna[cust.id] && (
                            <div style={{ borderTop: '1px solid var(--border-color)', padding: 'var(--space-4) var(--space-5)', display: 'flex', justifyContent: 'center' }}>
                              <div style={{ width: '100%', maxWidth: '550px' }}>
                                <StyleProfileCard customer={cust} />
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </>
            )}

            {/* 5b. CUSTOMER DETAIL VIEW (Image 5/6 extension) */}
            {dashboardTab === 'customers' && selectedDirectoryCustomer && (() => {
              const c = selectedDirectoryCustomer;
              const isOwner = !currentUser?.role || currentUser.role === 'Owner';
              const parts = c.measurements?.additional_measurements?.stitch_parts || [];
              const visible = c.measurements ? getVisibleMeasurementFields(parts) : [];
              const FIELDS = [['bust', 'Bust'], ['waist', 'Waist'], ['hips', 'Hips'], ['shoulder', 'Shoulder'],
                              ['arm_length', 'Arm Length'], ['neck', 'Neck'], ['length', 'Length']];
              const shown = FIELDS.filter(([k]) => visible.includes(k));
              const orders = c.orders || [];
              const orderCount = c.order_count ?? orders.length;
              // Both routes land in the order wizard, whose first step PATCHes
              // the customer, and RolePermission refuses partial_update for
              // anyone but the Owner -- so the buttons are the owner's.
              const goExisting = () => {
                setCustomerId(c.id);
                setCustomerForm({
                  ...DEFAULT_CUSTOMER_DATA,
                  ...c,
                  measurements: c.measurements || DEFAULT_CUSTOMER_DATA.measurements
                });
                if (c.design_preferences?.length > 0) {
                  setDesignNotes(c.design_preferences[0].notes || '');
                }
                setCurrentStep(3);
                setView('wizard');
              };
              const reorder = (order) => {
                setCustomerId(c.id);
                setCustomerForm({
                  ...DEFAULT_CUSTOMER_DATA,
                  ...c,
                  measurements: c.measurements || DEFAULT_CUSTOMER_DATA.measurements
                });
                // Garment prices are per garment now and the dresses are
                // re-added on step 3, so they re-quote there; only the
                // order-level money carries over.
                setQuotePrices({ packaging: order.packaging_handling, discount: order.discount || 0 });
                setCurrentStep(3);
                setView('wizard');
              };
              const statusTone = (st) => st === 'Delivered' ? 'success' : st === 'Cancelled' ? 'neutral' : 'warning';
              return (
              <div className="customer-detail-view-container at-stack">
                <div className="at-toolbar" style={{ margin: 0 }}>
                  <button type="button" className="at-link" onClick={() => setSelectedDirectoryCustomer(null)}>
                    <ArrowLeft size={16} /> Back to Customer Directory
                  </button>
                  {isOwner && (
                    <div className="at-toolbar-right">
                      <button className="btn-secondary" style={{ color: 'var(--accent-text)', borderColor: 'var(--accent-border)', background: 'var(--surface-color)' }} onClick={goExisting}>
                        <Copy size={16} /> Go with Existing Design
                      </button>
                      <button className="btn-primary" onClick={() => handleSelectExistingCustomer(c)}>
                        <Sparkles size={16} /> Create New Design
                      </button>
                    </div>
                  )}
                </div>

                <div className="ui-card at-profile-head">
                  <div className="at-profile-id">
                    <AvatarInitials name={`${c.first_name} ${c.last_name}`} size={96} tone="rose" />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                        <h2 className="at-page-title" style={{ fontSize: 'var(--text-2xl)' }}>{c.first_name} {c.last_name}</h2>
                        <SegmentBadge segment={c.segment} />
                      </div>
                      <div className="at-page-sub">{c.customer_type}{c.source ? ` · ${c.source}` : ''}</div>
                      <div className="at-contact" style={{ fontSize: 'var(--text-sm)', marginTop: '12px' }}>
                        <span><Phone size={14} /> {formatMobile(c.mobile_number)}</span>
                        {c.email_address && <span><Mail size={14} /> {c.email_address}</span>}
                        {(c.address || c.city_region) && (
                          <span><MapPin size={14} /> {[c.address, c.city_region].filter(Boolean).join(', ')}</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="at-profile-stats">
                    <div className="at-profile-stat">
                      <IconTile icon={CalendarDays} tone="blue" size={36} iconSize={16} />
                      <div><div className="at-measure-label">Customer since</div><div className="at-measure-value">{fmtDate(c.created_at)}</div></div>
                    </div>
                    <div className="at-profile-stat">
                      <IconTile icon={ShoppingBag} tone="amber" size={36} iconSize={16} />
                      <div><div className="at-measure-label">Total orders</div><div className="at-measure-value">{orderCount}</div></div>
                    </div>
                    <div className="at-profile-stat">
                      <IconTile icon={Heart} tone="rose" size={36} iconSize={16} />
                      <div><div className="at-measure-label">Preference</div><div className="at-measure-value">{c.occasion || c.garment_type || '—'}</div></div>
                    </div>
                  </div>
                </div>

                <div className="responsive-profile-grid">
                  <div className="at-stack">
                    <SectionCard icon={Ruler} tone="amber" title="Body Measurements & Sizing"
                                 subtitle={parts.length > 0 ? `Stitching: ${parts.join(', ')}` : undefined}>
                      {c.measurements ? (
                        <>
                          <div className="at-measure-cols">
                            {shown.map(([k, label]) => (
                              <div key={k} className="at-measure-row">
                                <span>{label}</span>
                                <strong>{c.measurements[k] ? `${c.measurements[k]} in` : '—'}</strong>
                              </div>
                            ))}
                            <div className="at-measure-row">
                              <span>Occasion Preference</span>
                              <strong>{c.occasion || '—'}</strong>
                            </div>
                          </div>
                          {c.measurement_history && c.measurement_history.length > 0 && (
                            <div style={{ marginTop: 'var(--space-4)' }}>
                              <div className="ui-eyebrow" style={{ color: 'var(--accent-text)', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: 'var(--space-3)' }}>
                                <History size={13} /> Sizing Version History
                              </div>
                              <div className="at-stack" style={{ gap: 'var(--space-2)', maxHeight: '300px', overflowY: 'auto', paddingRight: '4px' }}>
                                {[...c.measurement_history].reverse().map((hist, idx, arr) => (
                                  <div key={hist.id || idx} className="at-version">
                                    <div className="at-version-head">
                                      <strong style={{ color: 'var(--text-primary)' }}>Version {arr.length - idx}</strong>
                                      <span style={{ color: 'var(--text-secondary)' }}>{fmtDateTime(hist.changed_at)}</span>
                                    </div>
                                    <div className="at-version-grid">
                                      {FIELDS.filter(([k]) => visible.includes(k)).map(([k, label]) => (
                                        <span key={k}>{label.replace(' Length', '')} <strong>{hist[k] || '—'}</strong></span>
                                      ))}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </>
                      ) : (
                        <p style={{ color: 'var(--text-muted)', margin: 0 }}>No measurements saved yet.</p>
                      )}
                    </SectionCard>

                    <SectionCard icon={ShoppingBag} tone="amber" title="Order History"
                                 action={orders.length > 0 ? () => setDashboardTab('orders') : undefined} actionLabel="View All">
                      {directoryDetailLoading && !c.orders ? (
                        <p style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>Loading order history…</p>
                      ) : orders.length === 0 ? (
                        <p style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>No orders have been placed by this customer yet.</p>
                      ) : orders.map(order => {
                        // The row opens the order's production progress, so
                        // "where is my dress?" is answered from the profile.
                        const isOpen = expandedCustomerOrderId === order.id;
                        const stages = order.stages || [];
                        const done = stages.filter(st => st.status === 'COMPLETED').length;
                        const current = stages.find(st => st.status === 'IN_PROGRESS');
                        const toggle = () => setExpandedCustomerOrderId(isOpen ? null : order.id);
                        return (
                          <div key={order.id} className={`at-order-row${isOpen ? ' at-order-row--open' : ''}`}>
                            <div
                              role="button"
                              tabIndex={0}
                              className="at-order-row-head"
                              onClick={toggle}
                              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } }}
                            >
                              <div className="at-thumb at-tile--amber">
                                {order.completed_garment_image ? <img src={order.completed_garment_image} alt="" /> : <Shirt size={18} />}
                              </div>
                              <div className="at-row-main">
                                <div className="at-row-title">Order {orderRef(order)}</div>
                                <div className="at-row-sub">
                                  {order.garment_label || orderGarmentLabel(order)} · {order.tailor_name || 'Tailor not assigned'}
                                  {stages.length > 0 ? ` · ${done}/${stages.length} stages${current ? ` · ${current.stage_name}` : ''}` : ''}
                                </div>
                              </div>
                              <span className={`ui-badge ui-badge--${statusTone(order.order_status)}`}>{order.order_status}</span>
                              <span className="at-row-sub" style={{ whiteSpace: 'nowrap' }}>{fmtDate(order.order_date)}</span>
                              <strong className="at-num" style={{ color: 'var(--accent-text)' }}>{inr(order.total_amount)}</strong>
                              <ChevronRight size={16} style={{ transform: isOpen ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s', color: 'var(--text-muted)' }} />
                            </div>

                            {isOpen && (
                              <div className="at-order-row-body">
                                <StageTimeline
                                  stages={stages}
                                  onSelectStage={(stage) => openStageReview(order, stage)}
                                />
                                {stages.length > 0 && (
                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: '8px', marginTop: '12px' }}>
                                    {stages.map(stage => (
                                      <div key={stage.stage_key} style={{ fontSize: 'var(--text-2xs)', padding: '8px 10px', borderRadius: 'var(--radius-sm)', background: 'var(--surface-2)', border: '1px solid var(--border-color)' }}>
                                        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{stage.stage_name}</div>
                                        <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>
                                          {stage.status.replace('_', ' ').toLowerCase()}
                                          {stage.assigned_to_name ? ` · ${stage.assigned_to_name}` : ''}
                                        </div>
                                        {stage.completed_at && <div style={{ color: 'var(--text-muted)' }}>{fmtDate(stage.completed_at)}</div>}
                                      </div>
                                    ))}
                                  </div>
                                )}
                                <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: '12px' }}>
                                  <span>Payment: <strong style={{ color: 'var(--text-primary)' }}>{order.payment_status}</strong></span>
                                  <span>Delivery: <strong style={{ color: 'var(--text-primary)' }}>{order.delivery_method}</strong></span>
                                  {order.estimated_delivery && (
                                    <span>Expected: <strong style={{ color: 'var(--text-primary)' }}>{fmtDate(order.estimated_delivery)}</strong></span>
                                  )}
                                </div>
                                {isOwner && (
                                  <button type="button" className="btn-secondary at-btn-sm"
                                          style={{ marginTop: '12px', color: 'var(--accent-text)', borderColor: 'var(--accent-border)', background: 'var(--accent-color)' }}
                                          onClick={(e) => { e.stopPropagation(); reorder(order); }}>
                                    <Copy size={12} /> Reorder Style
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </SectionCard>
                  </div>

                  <div className="at-stack">
                    <StyleProfileCard customer={c} />

                    <SectionCard icon={ImageIcon} tone="green" title="Saved Designs & Inspiration">
                      {!c.design_preferences || c.design_preferences.length === 0 ? (
                        <p style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>No saved designs or reference images.</p>
                      ) : (
                        <div className="at-stack">
                          {c.design_preferences.map((pref, i) => (
                            <div key={pref.id || i} className="at-form-section" style={{ borderColor: pref.is_approved ? 'var(--success-color)' : undefined, gap: 'var(--space-3)' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                  <span className="ui-eyebrow">{pref.source_display || 'Boutique catalogue'}</span>
                                  {pref.is_approved && <span className="ui-badge ui-badge--success">Approved for production</span>}
                                </div>
                                {!pref.is_approved && pref.id && (
                                  <button type="button" className="btn-secondary at-btn-sm"
                                          disabled={approvingDesignId === pref.id}
                                          onClick={() => handleApproveDesign(pref.id, pref.reference_images?.[0])}>
                                    {approvingDesignId === pref.id ? 'Approving…' : 'Approve for production'}
                                  </button>
                                )}
                              </div>
                              {pref.notes && <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', margin: 0 }}>{pref.notes}</p>}
                              {pref.reference_images?.length > 0 && (
                                <div className="at-photos">
                                  {pref.reference_images.map((url, j) => (
                                    <span key={`${i}-${j}`} className="at-photo" style={{ width: 96, height: 120, borderColor: pref.approved_image === url ? 'var(--success-color)' : undefined, borderWidth: pref.approved_image === url ? 2 : 1 }}>
                                      <img src={url} alt="Design reference" />
                                    </span>
                                  ))}
                                </div>
                              )}
                              {pref.reference_links?.length > 0 && (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                  {pref.reference_links.map((link, j) => (
                                    <a key={j} href={link} target="_blank" rel="noreferrer" className="at-link" style={{ fontSize: 'var(--text-xs)', overflowWrap: 'anywhere', whiteSpace: 'normal' }}>
                                      {link}
                                    </a>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </SectionCard>
                  </div>
                </div>
              </div>
              );
            })()}

            {/* 6. INVOICES TAB */}

            {dashboardTab === 'invoices' && (() => {
              // Collected is what has actually been received, and outstanding
              // is the same (total - paid) expression the Balance Due cell in
              // every row below uses, so the header agrees with its own table.
              const paidTotal = ordersList.reduce((sum, o) => sum + parseFloat(o.amount_paid || 0), 0);
              const pendingTotal = ordersList.reduce((sum, o) => sum + Math.max(0, parseFloat(o.total_amount || 0) - parseFloat(o.amount_paid || 0)), 0);
              const grandTotal = ordersList.reduce((sum, o) => sum + parseFloat(o.total_amount), 0);
              const paidCount = ordersList.filter(o => o.payment_status === 'Paid').length;
              const pendingCount = ordersList.length - paidCount;
              const filtered = ordersList.filter(order => {
                if (invoiceFilter === 'Paid' && order.payment_status !== 'Paid') return false;
                if (invoiceFilter === 'Pending' && order.payment_status === 'Paid') return false;
                if (invoiceSearch.trim()) {
                  const query = invoiceSearch.toLowerCase();
                  const matchesId = order.order_id.toLowerCase().includes(query)
                    || orderRef(order).toLowerCase().includes(query);
                  const matchesClient = (order.customer_name || '').toLowerCase().includes(query);
                  return matchesId || matchesClient;
                }
                return true;
              });
              const statusTone = (st) => st === 'Paid' ? 'success' : st === 'Partially Paid' ? 'warning' : 'danger';
              return (
              <>
                <PageHeader
                  title={t('invoicesPage.title', 'Invoices & Billing')}
                  subtitle={t('invoicesPage.subtitle', 'Manage invoices, verify billing payments, and print receipts.')}
                  aside={(
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <UserAvatar user={currentUser} />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  )}
                />

                <section className="at-stat-grid">
                  <StatCard icon={Banknote} tone="green" label={t('invoicesPage.totalCollectedRevenue', 'Total Collected Revenue')}
                            value={formatMoney(paidTotal)} sub={`${paidCount} settled in full`} />
                  <StatCard icon={Wallet} tone="amber" label={t('invoicesPage.outstandingBalance', 'Outstanding Balance')}
                            value={formatMoney(pendingTotal)} sub={`across ${pendingCount} invoice${pendingCount === 1 ? '' : 's'}`} />
                  <StatCard icon={Receipt} tone="blue" label={t('invoicesPage.totalInvoicedVolume', 'Total Invoiced Volume')}
                            value={formatMoney(grandTotal)} sub={`${ordersList.length} invoice${ordersList.length === 1 ? '' : 's'}`} />
                </section>

                <div className="at-toolbar">
                  <Chips value={invoiceFilter} onChange={setInvoiceFilter} options={[
                    { key: 'All', label: t('common.all', 'All'), count: ordersList.length },
                    { key: 'Paid', label: t('invoicesPage.paid', 'Paid'), count: paidCount },
                    { key: 'Pending', label: t('invoicesPage.pending', 'Pending'), count: pendingCount },
                  ]} />
                  <div className="at-toolbar-right">
                    <SearchBox value={invoiceSearch} onChange={setInvoiceSearch}
                               placeholder={t('invoicesPage.searchPlaceholder', 'Search Invoice ID or Client...')} />
                  </div>
                </div>

                {paymentError && (
                  <div role="alert" style={{ marginBottom: '16px', background: 'var(--danger-bg)', border: '1px solid var(--danger-color)', color: 'var(--danger-color)', borderRadius: 'var(--radius-md)', padding: '12px 14px', fontSize: 'var(--text-sm)', display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                    <span>{paymentError}</span>
                    <button type="button" onClick={() => setPaymentError(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontWeight: 700 }}>Dismiss</button>
                  </div>
                )}

                <div className="invoices-content at-table-wrap">
                  <table className="at-table">
                    <thead>
                      <tr>
                        <th>{t('invoicesPage.invoiceId', 'Invoice ID')}</th>
                        <th>{t('invoicesPage.billingClient', 'Billing Client')}</th>
                        <th>{t('common.date', 'Date')}</th>
                        <th>{t('invoicesPage.totalPrice', 'Total Price')}</th>
                        <th>{t('invoicesPage.advancePaid', 'Advance Paid')}</th>
                        <th>{t('invoicesPage.totalPaid', 'Total Paid')}</th>
                        <th>{t('invoicesPage.balanceDue', 'Balance Due')}</th>
                        <th>{t('common.status', 'Payment Status')}</th>
                        <th>{t('common.actions', 'Action')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.length === 0 ? (
                        <tr>
                          <td colSpan="9" style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                            {ordersList.length === 0
                              ? t('invoicesPage.emptyState', 'Invoices appear here once you have created an order.')
                              : t('invoicesPage.noMatchingInvoices', 'No invoices matching the criteria.')}
                          </td>
                        </tr>
                      ) : filtered.map(order => {
                        const total = Number(order.total_amount) || 0;
                        const paid = Number(order.amount_paid || 0);
                        const balance = Math.max(0, total - paid);
                        const pct = total > 0 ? Math.round((paid / total) * 100) : 0;
                        return (
                          <tr key={order.id}>
                            <td style={{ fontWeight: 700 }}>{orderRef(order)}</td>
                            <td>
                              <span className="at-cell-person">
                                <AvatarInitials name={order.customer_name} size={32} />
                                <span style={{ fontWeight: 500 }}>{order.customer_name}</span>
                              </span>
                            </td>
                            <td style={{ color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{fmtDate(order.order_date)}</td>
                            <td className="at-num" style={{ fontWeight: 600 }}>{formatMoney(order.total_amount)}</td>
                            <td className="at-num" style={{ color: 'var(--text-secondary)' }}>{formatMoney(order.advance_paid)}</td>
                            {/* Editable: the one place a part payment is recorded. The
                                backend derives the label, clamps to the total and caps
                                the advance -- only the input lives here. */}
                            <td>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--success-color)', fontWeight: 600 }}>
                                <span>₹</span>
                                <input
                                  type="number"
                                  min="0"
                                  step="0.01"
                                  max={order.total_amount}
                                  defaultValue={parseFloat(order.amount_paid || 0)}
                                  disabled={savingPaymentId === order.id}
                                  aria-label={`Amount paid for invoice ${orderRef(order)}`}
                                  onBlur={async (e) => {
                                    const next = parseFloat(e.target.value);
                                    const current = parseFloat(order.amount_paid || 0);
                                    // Blur fires on every tab-through; only write
                                    // when the number actually moved.
                                    if (isNaN(next) || next === current) {
                                      e.target.value = current;
                                      return;
                                    }
                                    setSavingPaymentId(order.id);
                                    try {
                                      await api.updateOrder(order.id, { amount_paid: next });
                                      await fetchDashboardAndConfig();
                                    } catch (err) {
                                      e.target.value = current;
                                      setPaymentError(`Could not record that payment for ${orderRef(order)} — ${err.message}`);
                                    } finally {
                                      setSavingPaymentId(null);
                                    }
                                  }}
                                  onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur(); }}
                                  style={{ width: '100px', padding: '4px 6px', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--success-color)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', background: 'transparent' }}
                                />
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px', minWidth: '120px' }}>
                                <span style={{ flex: 1 }}><ProgressBar pct={pct} tone="green" /></span>
                                <span className="at-num" style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-secondary)' }}>{pct}%</span>
                              </div>
                            </td>
                            <td className="at-num" style={{ color: balance > 0 ? 'var(--danger-color)' : 'var(--text-secondary)', fontWeight: 600 }}>
                              {formatMoney(balance)}
                            </td>
                            <td>
                              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                                <span className={`ui-badge ui-badge--${statusTone(order.payment_status)}`}>{order.payment_status}</span>
                                <select
                                  value={order.payment_status}
                                  disabled={savingPaymentId === order.id}
                                  aria-label={`Payment status for invoice ${orderRef(order)}`}
                                  onChange={async (e) => {
                                    setSavingPaymentId(order.id);
                                    try {
                                      await api.updateOrder(order.id, { payment_status: e.target.value });
                                      fetchDashboardAndConfig();
                                    } catch (err) {
                                      e.target.value = order.payment_status;
                                      setPaymentError(`Could not update ${orderRef(order)} — ${err.message}`);
                                    } finally {
                                      setSavingPaymentId(null);
                                    }
                                  }}
                                  className="form-control"
                                  style={{ padding: '4px 8px', fontSize: '12px', width: '110px', margin: 0 }}
                                >
                                  {/* "Partially Paid" is a *derived* label, not a thing to
                                      choose; it appears only as the current value. */}
                                  <option value="Pending">{t('invoicesPage.pending', 'Pending')}</option>
                                  {order.payment_status === 'Partially Paid' && (
                                    <option value="Partially Paid">{t('invoicesPage.partiallyPaid', 'Partially Paid')}</option>
                                  )}
                                  <option value="Paid">{t('invoicesPage.paid', 'Paid')}</option>
                                </select>
                              </span>
                            </td>
                            <td>
                              <button className="btn-secondary at-btn-sm" onClick={() => {
                                setConfirmedOrder(order);
                                setShowInvoiceModal(true);
                              }}>
                                <FileText size={12} /> {t('invoicesPage.viewInvoice', 'View Invoice')}
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
              );
            })()}

            {/* 7. ANALYTICS TAB */}
            {dashboardTab === 'analytics' && (() => {
              // Same definition as the Invoices header and the Balance Due
              // cells: collected is money received, not the face value of
              // orders that happen to be labelled Paid.
              const paidRevenue = ordersList.reduce((sum, o) => sum + parseFloat(o.amount_paid || 0), 0);
              const totalBilling = ordersList.reduce((sum, o) => sum + parseFloat(o.total_amount || 0), 0);
              const pendingBill = Math.max(0, totalBilling - paidRevenue);
              const aov = ordersList.length > 0 ? (totalBilling / ordersList.length) : 0;

              // Counted per garment ordered, not per customer: the order wizard
              // writes neckline and sleeve onto the garment job, never onto the
              // customer, and a blouse-and-lehenga order is two garments.
              const garmentDist = {};
              const necklineDist = {};
              const sleeveDist = {};
              let garmentTotal = 0;
              const tally = (dist, value) => {
                if (value === undefined || value === null || value === '') return;
                const label = humaniseSpecKey(value);
                dist[label] = (dist[label] || 0) + 1;
              };
              ordersList.forEach(o => {
                orderGarmentNames(o).forEach(name => {
                  garmentDist[name] = (garmentDist[name] || 0) + 1;
                  garmentTotal += 1;
                });
                (o.garment_jobs || []).forEach(job => {
                  tally(necklineDist, job.spec?.front_neck);
                  tally(sleeveDist, job.spec?.sleeve_length);
                });
              });

              const topGarmentsList = Object.entries(garmentDist).sort((a, b) => b[1] - a[1]).slice(0, 4);
              const topNecklinesList = Object.entries(necklineDist).sort((a, b) => b[1] - a[1]).slice(0, 4);
              const topSleevesList = Object.entries(sleeveDist).sort((a, b) => b[1] - a[1]).slice(0, 4);

              const busyTailors = tailors.filter(t => t.status === 'Busy').length;
              const avgTailorRating = tailors.length > 0 ? (tailors.reduce((sum, t) => sum + parseFloat(t.rating), 0) / tailors.length) : 5.0;

              const segments = (() => {
                const total = customersList.length || 1;
                const rows = [
                  { name: t('analyticsPage.hvcCustomer', 'HVC (High Value Customer)'), count: customersList.filter(c => c.segment === 'HVC').length, color: '#6b4fd6' },
                  { name: t('analyticsPage.vipCustomer', 'VIP (Very Important Customer)'), count: customersList.filter(c => c.segment === 'VIP').length, color: '#d4af37' },
                  { name: t('analyticsPage.generalCustomers', 'General Customers'), count: customersList.filter(c => c.segment === 'General').length, color: '#9ca3af' },
                ].map(r => ({ ...r, pct: Math.round((r.count / total) * 100) }));
                let acc = 0;
                const stops = rows.map(r => { const from = acc; acc += (r.count / total) * 100; return `${r.color} ${from}% ${acc}%`; });
                return { rows, gradient: `conic-gradient(${stops.join(', ')}${acc < 100 ? `, var(--surface-inset) ${acc}% 100%` : ''})` };
              })();

              const bar = (label, count, total, tone) => {
                const pct = Math.round((count / (total || 1)) * 100) || 0;
                return (
                  <div key={label} className="at-bar-row">
                    <div className="at-bar-head">
                      <span>{label}</span>
                      <span className="at-num" style={{ fontWeight: 600 }}>{count} ({pct}%)</span>
                    </div>
                    <ProgressBar pct={pct} tone={tone} />
                  </div>
                );
              };

              return (
                <>
                  <PageHeader
                    title={t('analyticsPage.title', 'Business Analytics & Trends')}
                    subtitle={t('analyticsPage.subtitle', 'Summary of revenues, style preferences, and operations workload.')}
                    aside={(
                      <div className="user-profile-widget">
                        <div className="user-avatar-circle">
                          <UserAvatar user={currentUser} />
                        </div>
                        <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                      </div>
                    )}
                  />

                  <section className="at-stat-grid" style={{ marginBottom: 'var(--space-5)' }}>
                    <StatCard icon={Coins} tone="green" label={t('analyticsPage.collectedRevenue', 'Collected Revenue')}
                              value={inr(paidRevenue)} sub={t('analyticsPage.fromPaidOrders', 'From paid customer orders')} />
                    <StatCard icon={Receipt} tone="amber" label={t('analyticsPage.pendingInvoices', 'Pending Invoices')}
                              value={inr(pendingBill)} sub={t('analyticsPage.awaitingPayment', 'Awaiting full or partial payment')} />
                    <StatCard icon={BarChart2} tone="blue" label={t('analyticsPage.avgTicketSize', 'Average Ticket Size')}
                              value={inr(aov)} sub={t('analyticsPage.perBespokeOrder', 'Per bespoke order')} />
                    <StatCard icon={Users} tone="violet" label={t('analyticsPage.clientBase', 'Client Base')}
                              value={`${customersList.length} ${customersList.length === 1 ? t('analyticsPage.clientSingle', 'Client') : t('analyticsPage.clientPlural', 'Clients')}`}
                              sub={t('analyticsPage.totalDirectoryProfiles', 'Total boutique directory profiles')} />
                  </section>

                  <div className="at-grid-2">
                    <div className="at-stack">
                      <SectionCard icon={Shirt} tone="green" title={t('analyticsPage.popularGarmentTypes', 'Popular Garment Types')}
                                   subtitle="Most ordered garment categories" action={() => setDashboardTab('orders')}>
                        {topGarmentsList.length === 0 ? (
                          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>No garments ordered yet.</div>
                        ) : (
                          <div className="at-stack" style={{ gap: 'var(--space-3)' }}>
                            {topGarmentsList.map(([garment, count]) => bar(garment, count, garmentTotal, 'forest'))}
                          </div>
                        )}
                      </SectionCard>

                      <SectionCard icon={Users} tone="violet" title={t('analyticsPage.customerSegmentation', 'Customer Segmentation')}
                                   subtitle="Client distribution by value" action={() => setDashboardTab('customers')}>
                        <div style={{ display: 'flex', gap: 'var(--space-6)', alignItems: 'center', flexWrap: 'wrap' }}>
                          <div className="at-donut" style={{ background: segments.gradient }}>
                            <div className="at-donut-label">
                              <span className="at-donut-value">{customersList.length}</span>
                              <span className="at-donut-sub">Clients</span>
                            </div>
                          </div>
                          <div className="at-legend">
                            {segments.rows.map(seg => (
                              <div key={seg.name} className="at-legend-row">
                                <span className="at-legend-dot" style={{ background: seg.color }} />
                                <span style={{ flex: 1 }}>{seg.name}</span>
                                <span className="at-num" style={{ fontWeight: 600 }}>{seg.count} ({seg.pct}%)</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </SectionCard>

                      <SectionCard icon={PenTool} tone="amber" title={t('analyticsPage.necklineSleeveTrends', 'Neckline & Sleeve Trends')}
                                   subtitle="What is being asked for at the counter">
                        <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                          <div>
                            <div className="ui-eyebrow" style={{ marginBottom: '8px' }}>{t('analyticsPage.topNecklines', 'Top Necklines')}</div>
                            {topNecklinesList.length === 0 && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>None recorded yet.</div>}
                            {topNecklinesList.map(([style, count]) => (
                              <div key={style} style={{ fontSize: 'var(--text-sm)', display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                                <span>{style}</span>
                                <span className="at-num" style={{ fontWeight: 600 }}>{count}</span>
                              </div>
                            ))}
                          </div>
                          <div>
                            <div className="ui-eyebrow" style={{ marginBottom: '8px' }}>{t('analyticsPage.topSleeves', 'Top Sleeves')}</div>
                            {topSleevesList.length === 0 && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>None recorded yet.</div>}
                            {topSleevesList.map(([style, count]) => (
                              <div key={style} style={{ fontSize: 'var(--text-sm)', display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                                <span>{style}</span>
                                <span className="at-num" style={{ fontWeight: 600 }}>{count}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </SectionCard>
                    </div>

                    <div className="at-stack">
                      <SectionCard icon={Scissors} tone="blue" title={t('analyticsPage.staffWorkloadOverview', 'Staff & Workload Overview')}
                                   subtitle="Current team status and capacity" action={() => setDashboardTab('staff')} actionLabel="Manage Staff">
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 'var(--space-3)' }}>
                          <div className="at-pipeline-tile at-stat--blue" style={{ cursor: 'default' }}>
                            <span className="at-pipeline-label">{t('analyticsPage.totalTailoringTeam', 'Total Tailoring Team')}</span>
                            <span className="at-pipeline-value">{tailors.length} <small style={{ fontSize: 'var(--text-xs)', fontWeight: 500 }}>{tailors.length === 1 ? t('analyticsPage.tailorSingle', 'Tailor') : t('analyticsPage.tailorPlural', 'Tailors')}</small></span>
                          </div>
                          <div className="at-pipeline-tile at-stat--amber" style={{ cursor: 'default' }}>
                            <span className="at-pipeline-label">{t('analyticsPage.busyAssignedTailors', 'Busy / Assigned Tailors')}</span>
                            <span className="at-pipeline-value" style={{ color: 'var(--tone-amber-fg)' }}>{busyTailors} <small style={{ fontSize: 'var(--text-xs)', fontWeight: 500 }}>{t('analyticsPage.busyStatus', 'Busy')}</small></span>
                          </div>
                          <div className="at-pipeline-tile at-stat--green" style={{ cursor: 'default' }}>
                            <span className="at-pipeline-label">{t('analyticsPage.availableStaffCapacity', 'Available Staff capacity')}</span>
                            <span className="at-pipeline-value" style={{ color: 'var(--tone-green-fg)' }}>{tailors.length - busyTailors} <small style={{ fontSize: 'var(--text-xs)', fontWeight: 500 }}>{t('analyticsPage.freeStatus', 'Free')}</small></span>
                          </div>
                          <div className="at-pipeline-tile at-stat--violet" style={{ cursor: 'default' }}>
                            <span className="at-pipeline-label">{t('analyticsPage.atelierAvgRating', 'Atelier Average Rating')}</span>
                            <span className="at-pipeline-value">⭐ {avgTailorRating.toFixed(2)} <small style={{ fontSize: 'var(--text-xs)', fontWeight: 500 }}>out of 5</small></span>
                          </div>
                        </div>
                      </SectionCard>

                      <SectionCard icon={FileText} tone="green" title={t('analyticsPage.orderStatusBreakdown', 'Order Status Breakdown')}
                                   subtitle="Current order distribution" action={() => setDashboardTab('orders')}>
                        <div className="at-stack" style={{ gap: 'var(--space-3)' }}>
                          {Object.entries(dashboardData?.stats?.status_distribution || {})
                            .sort((a, b) => b[1] - a[1])
                            .map(([status, count]) => bar(t(`status.${status}`, status), count, ordersList.length, 'forest'))}
                        </div>
                      </SectionCard>
                    </div>
                  </div>
                </>
              );
            })()}

            {/* 8. MY ACCOUNT SETTINGS TAB */}
            {dashboardTab === 'account' && (() => {
              const isOwner = !currentUser?.role || currentUser.role === 'Owner';
              const tenant = localStorage.getItem('tenant_id') || '--';
              const copyText = (text) => navigator.clipboard?.writeText(text);
              return (
              <>
                <PageHeader
                  title={t('accountPage.title')}
                  subtitle={t('accountPage.subtitle')}
                  aside={(
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <UserAvatar user={currentUser} />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  )}
                />

                <div className="account-settings-container at-account">
                  <div className="ui-card at-account-card">
                    <div className="at-cover" />
                    <div className="at-account-avatar">
                      <div className="at-account-avatar-ring">
                        <UserAvatar user={currentUser} />
                      </div>
                      {/* Editable by any signed-in user -- the photo is stored
                          per-user (UserAvatar), so the owner can set theirs too. */}
                      <label className="at-account-camera" title="Change photo">
                        <Camera size={16} />
                        <input type="file" accept="image/*" hidden
                               onChange={async (e) => {
                                 const f = e.target.files?.[0];
                                 if (!f) return;
                                 try {
                                   const updated = await api.updateMyPhoto(f);
                                   setCurrentUser(updated);
                                 } catch (err) {
                                   alert(err.message || 'Could not update your photo.');
                                 }
                               }} />
                      </label>
                    </div>
                    <h3 className="at-account-name">{currentUser.first_name} {currentUser.last_name}</h3>
                    {/* The signed-in role, not a hardcoded claim. */}
                    <span className="ui-badge ui-badge--neutral">{currentUser.role || 'Boutique Owner'}</span>

                    <div className="at-account-rows">
                      <div className="at-account-row">
                        <Globe size={16} />
                        <div>
                          <div className="at-measure-label">{t('accountPage.tenantDomain', 'Tenant Domain')}</div>
                          <div className="at-measure-value" style={{ overflowWrap: 'anywhere' }}>{tenant}</div>
                        </div>
                        {tenant !== '--' && (
                          <button type="button" className="at-modal-close" style={{ width: 30, height: 30 }} onClick={() => copyText(tenant)} aria-label="Copy tenant domain">
                            <Copy size={13} />
                          </button>
                        )}
                      </div>
                      <div className="at-account-row">
                        <Mail size={16} />
                        <div>
                          <div className="at-measure-label">{t('accountPage.atelierEmail', 'Atelier Email')}</div>
                          <div className="at-measure-value" style={{ overflowWrap: 'anywhere' }}>{currentUser.email}</div>
                        </div>
                        {currentUser.email && (
                          <button type="button" className="at-modal-close" style={{ width: 30, height: 30 }} onClick={() => copyText(currentUser.email)} aria-label="Copy email">
                            <Copy size={13} />
                          </button>
                        )}
                      </div>
                      <div className="at-account-row">
                        <ShieldCheck size={16} />
                        <div>
                          <div className="at-measure-label">Role</div>
                          <div className="at-measure-value">{currentUser.role || 'Owner'}</div>
                        </div>
                      </div>
                      {/* No "Member since": nothing in the API carries the
                          tenant's created_on, and an absent fact beats a
                          confident wrong one. */}
                    </div>
                  </div>

                  {/* Owner only: submitting POSTs /boutique-settings/, which
                      RolePermission refuses for every other role. A form that
                      cannot succeed should not be drawn. */}
                  {isOwner && (
                    <SectionCard icon={Store} tone="green" title={t('accountPage.editProfile', 'Edit Boutique Profile')}
                                 subtitle="Keep your boutique information up to date. This will be visible across the platform.">
                      <form
                        className="at-stack"
                        onReset={() => setLogoFile(null)}
                        onSubmit={async (e) => {
                          e.preventDefault();
                          if (settingsSaving) return;
                          const form = e.target;
                          const formData = new FormData();
                          formData.append('name', form.boutiqueName.value);
                          formData.append('address', form.boutiqueAddress.value);
                          formData.append('phone', form.boutiquePhone.value);
                          formData.append('email', form.boutiqueEmail.value);
                          if (logoFile) {
                            formData.append('logo', logoFile);
                          }
                          formData.append('design_approval_required', form.designApprovalRequired.checked);
                          setSettingsSaving(true);
                          try {
                            const updated = await api.updateBoutiqueSettings(formData);
                            setBoutiqueSettings(updated);
                            setLogoFile(null);
                            alert("Boutique settings updated successfully!");
                          } catch (err) {
                            console.error(err);
                            alert("Failed to update boutique settings");
                          } finally {
                            setSettingsSaving(false);
                          }
                        }}
                      >
                        <Field label={t('accountPage.boutiqueName', 'Boutique Name')} required icon={Building2}>
                          <input type="text" name="boutiqueName" className="form-control"
                                 defaultValue={boutiqueSettings?.name || ''} placeholder="e.g. Aditi's Atelier" required />
                        </Field>
                        <Field label={t('accountPage.boutiqueAddress', 'Boutique Address')} required icon={MapPin}>
                          <textarea name="boutiqueAddress" className="form-control" rows={3}
                                    defaultValue={boutiqueSettings?.address || ''} placeholder="Street, area, city, PIN" required />
                        </Field>
                        <div className="at-form-grid">
                          <Field label={t('accountPage.boutiquePhone', 'Boutique Phone')} required icon={Phone}>
                            <input type="text" name="boutiquePhone" className="form-control"
                                   defaultValue={boutiqueSettings?.phone || ''} placeholder="+91 98765 43210" required />
                          </Field>
                          <Field label={t('accountPage.boutiqueEmail', 'Boutique Email')} required icon={Mail}>
                            <input type="email" name="boutiqueEmail" className="form-control"
                                   defaultValue={boutiqueSettings?.email || ''} placeholder="you@yourboutique.com" required />
                          </Field>
                        </div>

                        <div className="at-field">
                          <span className="at-field-label">{t('accountPage.boutiqueLogo', 'Boutique Logo')}</span>
                          <div className="at-side-by-side">
                            {(logoFile || boutiqueSettings?.logo) ? (
                              <div className="at-form-section" style={{ flexDirection: 'row', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                                <img src={logoFile ? URL.createObjectURL(logoFile) : boutiqueSettings.logo} alt="Boutique logo"
                                     style={{ width: 56, height: 56, objectFit: 'contain', borderRadius: '8px', background: 'var(--surface-inset)', border: '1px solid var(--border-color)' }} />
                                <div className="at-row-main">
                                  <div className="at-row-title">{logoFile ? logoFile.name : 'Current logo'}</div>
                                  <div className="at-row-sub">{logoFile ? 'Saved when you press Save Changes.' : 'Choose a file to replace it.'}</div>
                                </div>
                                <button type="button" className="btn-secondary at-btn-sm" onClick={() => document.getElementById('boutique-logo-file').click()}>
                                  <Upload size={14} /> Choose file
                                </button>
                                {logoFile && (
                                  <button type="button" className="btn-secondary at-btn-sm" onClick={() => setLogoFile(null)}>Remove</button>
                                )}
                                <input id="boutique-logo-file" type="file" accept="image/*" hidden
                                       onChange={(e) => setLogoFile(e.target.files?.[0] || null)} />
                              </div>
                            ) : (
                              <Dropzone camera
                                        title="Drag & drop your logo here" subtitle="or choose a file from your device"
                                        chooseLabel="Choose File" cameraLabel="Take photo"
                                        onFiles={(files) => setLogoFile(files[0] || null)} />
                            )}
                            <InfoNote tone="green" icon={ShieldCheck} title="Logo Guidelines"
                                      items={['Recommended size: 512 × 512 px', 'Formats: PNG, JPG (Max 2MB)', 'Square image works best', 'This logo will appear on invoices and customer communication.']} />
                          </div>
                        </div>

                        {/* Off by default: a small team is usually the owner and
                            one or two designers, and a queue with nobody to clear
                            it is friction with no benefit. */}
                        <label className="at-switch-row">
                          <IconTile icon={Settings} tone="neutral" size={36} iconSize={16} />
                          <span className="at-row-main">
                            <span className="at-row-title">{t('accountPage.requireApproval', 'Require approval for new designs')}</span>
                            <span className="at-row-sub" style={{ display: 'block' }}>
                              {t('accountPage.approvalHelp', 'When on, uploads from staff other than you wait for your review before appearing in the library.')}
                            </span>
                          </span>
                          <span className="at-switch">
                            <input type="checkbox" name="designApprovalRequired" defaultChecked={!!boutiqueSettings?.design_approval_required} />
                            <i />
                          </span>
                        </label>

                        <div className="at-form-foot">
                          <button type="reset" className="btn-secondary">{t('common.cancel', 'Cancel')}</button>
                          <button type="submit" className="btn-primary" disabled={settingsSaving}>
                            <Save size={16} /> {settingsSaving ? t('common.saving', 'Saving…') : t('accountPage.saveChanges', 'Save Changes')}
                          </button>
                        </div>
                      </form>
                    </SectionCard>
                  )}
                </div>
              </>
              );
            })()}

            {/* 9. SETTINGS TAB */}
            {dashboardTab === 'settings' && (
              <SettingsPage
                currentUser={currentUser}
                boutiqueSettings={boutiqueSettings}
                whatsappStatus={whatsappStatus}
                fetchWhatsAppStatus={fetchWhatsAppStatus}
              />
            )}
          </main>

          {/* Fabrics CRUD Modal Overlay */}
          {showFabricModal && (
            <FormModal
              icon={Layers} tone="green" zIndex={1100} width="720px"
              title={editingFabric ? t('fabricsPage.editFabricDetails', 'Edit Fabric Details') : t('fabricsPage.addNewFabricTitle', 'Add New Fabric to Catalog')}
              subtitle="Add fabric details to your catalog for easy selection and reuse."
              onClose={() => setShowFabricModal(false)}
              footer={(
                <>
                  <button type="button" className="btn-secondary" onClick={() => setShowFabricModal(false)}>{t('common.cancel', 'Cancel')}</button>
                  <button type="submit" form="fabric-form" className="btn-primary" disabled={fabricSaving || fabricUploads > 0}>
                    <Save size={16} />
                    {fabricUploads > 0
                      ? t('common.uploading', 'Uploading…')
                      : fabricSaving ? t('common.saving', 'Saving…')
                        : fabricCount > 1
                          ? `Save ${fabricCount} materials`
                          : t('fabricsPage.saveFabric', 'Save Fabric')}
                  </button>
                </>
              )}
            >
              <form id="fabric-form" onSubmit={handleSaveFabric} className="at-stack">
                {fabricGroups.map((group, i) => (
                  <FabricGroup
                    key={group._id}
                    index={i}
                    taxonomy={fabricTaxonomy}
                    value={group}
                    allowRepeat={!editingFabric}
                    canRemove={!editingFabric && fabricGroups.length > 1}
                    onUploading={(delta) => setFabricUploads(n => Math.max(0, n + delta))}
                    onChange={(next) => setFabricGroups(
                      rows => rows.map((row, idx) => (idx === i ? next : row)))}
                    onRemove={() => setFabricGroups(
                      rows => rows.filter((_, idx) => idx !== i))}
                  />
                ))}

                {!editingFabric && (
                  <button
                    type="button"
                    className="btn-secondary at-btn-sm"
                    style={{ alignSelf: 'flex-start', borderStyle: 'dashed' }}
                    onClick={() => setFabricGroups(rows => [...rows, blankGroup()])}
                  >
                    <Plus size={14} /> Add another garment or accessory
                  </button>
                )}
              </form>
            </FormModal>
          )}

          {/* Appointment booking. apps/scheduling has always accepted these and
              the customer's tracking page already renders a trial card from
              them; there was simply no way to create one from the product. */}
          {showAppointmentModal && (
            <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100 }}>
              <div className="search-modal-card" style={{ maxWidth: '460px', width: '100%' }}>
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)' }}>
                    {editingAppointment
                      ? t('dashboard.appointmentDetails', 'Appointment Details')
                      : t('dashboard.bookAppointment', 'Book an Appointment')}
                  </h3>
                  <button className="close-btn" onClick={closeAppointmentModal}><X size={20} /></button>
                </div>
                <form onSubmit={handleSaveAppointment} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div>
                    <label className="form-label">Client *</label>
                    {/* Whose appointment this is cannot be edited -- moving it
                        to another person is a different booking. */}
                    <select className="form-control" required disabled={!!editingAppointment}
                            value={appointmentForm.customer}
                            onChange={(e) => setAppointmentForm({ ...appointmentForm, customer: e.target.value })}>
                      <option value="">Select a client</option>
                      {allCustomers.map(c => (
                        <option key={c.id} value={c.id}>{c.first_name} {c.last_name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="form-label">Type</label>
                    <select className="form-control"
                            value={appointmentForm.appointment_type}
                            onChange={(e) => setAppointmentForm({ ...appointmentForm, appointment_type: e.target.value })}>
                      {Object.entries(APPOINTMENT_TYPE_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="form-label">Date & time *</label>
                    <input className="form-control" type="datetime-local" required
                           value={appointmentForm.scheduled_time}
                           onChange={(e) => setAppointmentForm({ ...appointmentForm, scheduled_time: e.target.value })} />
                  </div>
                  <div>
                    <label className="form-label">With</label>
                    <select className="form-control"
                            value={appointmentForm.assigned_staff}
                            onChange={(e) => setAppointmentForm({ ...appointmentForm, assigned_staff: e.target.value })}>
                      <option value="">Unassigned</option>
                      {tailors.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                  </div>
                  {editingAppointment && (
                    <div>
                      <label className="form-label">Status</label>
                      <select className="form-control"
                              value={appointmentForm.status}
                              onChange={(e) => setAppointmentForm({ ...appointmentForm, status: e.target.value })}>
                        {Object.entries(APPOINTMENT_STATUS_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div>
                    <label className="form-label">Notes</label>
                    <textarea className="form-control" rows={2}
                              value={appointmentForm.notes}
                              onChange={(e) => setAppointmentForm({ ...appointmentForm, notes: e.target.value })} />
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', justifyContent: 'flex-end' }}>
                    {editingAppointment && appointmentForm.status !== 'CANCELLED' && (
                      <button type="button" className="btn-secondary" disabled={savingAppointment}
                              style={{ marginRight: 'auto', color: '#c0392b', borderColor: 'rgba(192,57,43,0.3)' }}
                              onClick={handleCancelAppointment}>
                        {t('dashboard.cancelAppointment', 'Cancel appointment')}
                      </button>
                    )}
                    <button type="button" className="btn-secondary" onClick={closeAppointmentModal}>
                      {t('common.close', 'Close')}
                    </button>
                    <button type="submit" className="btn-primary" disabled={savingAppointment}>
                      {savingAppointment
                        ? t('common.saving', 'Saving…')
                        : editingAppointment
                          ? t('common.saveChanges', 'Save changes')
                          : t('dashboard.bookAppointmentBtn', 'Book appointment')}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}



          {/* Designs CRUD Modal Overlay */}
          {showDesignModal && (
            <FormModal
              icon={Shirt} tone="amber" zIndex={1100} width="720px"
              title={editingDesign ? t('designsPage.editDesignDetails', 'Edit Design Details') : t('designsPage.addNewDesignTitle', 'Add New Design to Collection')}
              subtitle="Add garment details to your boutique collection."
              onClose={() => setShowDesignModal(false)}
              footer={(
                <>
                  <button type="button" className="btn-secondary" onClick={() => setShowDesignModal(false)}>{t('common.cancel', 'Cancel')}</button>
                  <button type="submit" form="design-form" className="btn-primary" disabled={designSaving}>
                    <Save size={16} /> {designSaving ? t('common.saving', 'Saving…') : t('designsPage.saveDesign', 'Save Design')}
                  </button>
                </>
              )}
            >
              <form id="design-form" onSubmit={handleSaveDesign} className="at-stack">
                <Field label={t('designsPage.designName', 'Design Name')} required icon={Type}>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. Royal Maroon Velvet Lehenga"
                    value={designForm.name}
                    onChange={e => setDesignForm({...designForm, name: e.target.value})}
                  />
                </Field>

                <div className="at-form-grid">
                  <Field label={t('designsPage.garmentCategory', 'Garment Category')} required icon={Shirt}>
                    <select
                      className="form-control"
                      value={designForm.garment_type}
                      onChange={e => setDesignForm({...designForm, garment_type: e.target.value, catalogue: {}, catalogue_path: null})}
                    >
                      <option value="Lehenga">{t('designsPage.lehenga', 'Lehenga')}</option>
                      <option value="Gown">{t('designsPage.gown', 'Gown')}</option>
                      <option value="Saree">{t('designsPage.saree', 'Saree')}</option>
                      <option value="Kurti">{t('designsPage.kurti', 'Kurti')}</option>
                      <option value="Sherwani">{t('designsPage.sherwani', 'Sherwani')}</option>
                      <option value="Anarkali">{t('designsPage.anarkali', 'Anarkali')}</option>
                    </select>
                  </Field>
                  <Field label={t('designsPage.designType', 'Design Type')} required icon={Tag}>
                    <select
                      className="form-control"
                      value={designForm.is_boutique}
                      onChange={e => setDesignForm({...designForm, is_boutique: e.target.value === 'true' || e.target.value === true})}
                    >
                      <option value="true">{t('designsPage.boutiqueCatalogCollection', 'Boutique Catalog Collection')}</option>
                      <option value="false">{t('designsPage.aiSuggestionTemplate', 'AI Suggestion Template')}</option>
                    </select>
                  </Field>
                  {/* Where in the garment's design catalogue this design is
                      filed. The garment here is a name ("Saree"); the
                      catalogue is keyed the way templates are, so the name is
                      slugged the same way the server will slug it. Nothing
                      renders for a garment without a catalogue. */}
                  <DesignCataloguePicker
                    garmentKey={(designForm.garment_type || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')}
                    value={designForm.catalogue || {}}
                    onChange={(value, payload) => setDesignForm({ ...designForm, catalogue: value, catalogue_path: payload })}
                  />
                  <Field label={t('designsPage.necklineStyleOptional', 'Neckline Style (Optional)')} icon={Sparkles}>
                    <input
                      type="text"
                      className="form-control"
                      placeholder="e.g. Sweetheart Neck"
                      value={designForm.neckline_style}
                      onChange={e => setDesignForm({...designForm, neckline_style: e.target.value})}
                    />
                  </Field>
                  <Field label={t('designsPage.sleeveStyleOptional', 'Sleeve Style (Optional)')} icon={Shirt}>
                    <input
                      type="text"
                      className="form-control"
                      placeholder="e.g. Cap Sleeve"
                      value={designForm.sleeve_style}
                      onChange={e => setDesignForm({...designForm, sleeve_style: e.target.value})}
                    />
                  </Field>
                </div>

                <Field label={t('designsPage.catalogPriceLabel', 'Catalog Price (₹) - Only for Boutique Catalog')} icon={IndianRupee}>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    className="form-control"
                    placeholder="e.g. 45000"
                    value={designForm.price}
                    onChange={e => setDesignForm({...designForm, price: e.target.value})}
                    disabled={designForm.is_boutique === false || designForm.is_boutique === 'false'}
                  />
                </Field>

                <Field label={t('designsPage.imageUrlOptional', 'Image URL (Optional)')} icon={LinkIcon}
                       hint="Add a link if the image is hosted online.">
                  <input
                    type="url"
                    className="form-control"
                    placeholder="e.g. https://images.unsplash.com/photo-..."
                    value={designForm.image_url}
                    onChange={e => setDesignForm({...designForm, image_url: e.target.value})}
                  />
                </Field>

                <Field label={t('designsPage.descriptionOptional', 'Description (Optional)')} icon={FileText}>
                  <textarea
                    className="form-control"
                    placeholder="e.g. Hand-embroidered with gold thread, georgette base..."
                    rows="3"
                    value={designForm.description}
                    onChange={e => setDesignForm({...designForm, description: e.target.value})}
                  />
                </Field>
                <div className="at-field-counter" style={{ marginTop: '-8px' }}>{(designForm.description || '').length} characters</div>

                <InfoNote tone="amber" title="Tip">
                  High quality images and detailed descriptions help showcase your designs better.
                </InfoNote>
              </form>
            </FormModal>
          )}

          {/* Bottom navigation, phones only.
              It belongs to this view, not the order selector it was originally
              written into: its tabs drive dashboardTab, which only the dashboard
              renders, so from anywhere else every tab was inert. */}
          <BottomNavigation
            tabs={[
              ...navSections.flatMap((s) => s.items).filter((i) => i.phone)
                .map((i) => ({ key: i.tab, label: i.phoneLabel || i.label, icon: i.icon })),
              { key: 'more', label: t('nav.menu', 'Menu'), icon: Menu }
            ]}
            activeTab={dashboardTab}
            onChangeTab={(tab) => { setDashboardTab(tab); setSelectedDirectoryCustomer(null); }}
            onOpenMore={() => setMobileNavOpen(true)}
          />
        </div>
      )}

      {/* 5. ORDER TYPE SELECTOR (Image 5) */}
      {view === 'order-selector' && (
        <div className={`portal-layout${navCollapsed ? ' nav-collapsed' : ''}`}>
          {/* Below 1024px .portal-sidebar is an off-canvas drawer. Without a way
              to open it -- and without the overlay to shut it again -- this
              screen had no navigation at all on a phone: the sidebar sat parked
              at translateX(-100%) and nothing on the page could bring it back. */}
          <MobileHeader
            title="New Order"
            currentUser={currentUser}
            notificationsCount={notifications.filter(n => !n.is_read).length}
            onOpenMenu={() => setMobileNavOpen(!mobileNavOpen)}
            onOpenNotifications={() => {
              setShowNotificationsDrawer(true);
              if (markingNotificationsRead) return;
              setMarkingNotificationsRead(true);
              api.markNotificationsAsRead(currentUser?.role || 'Owner', currentUser?.email)
                .then(() => fetchNotifications())
                    // Never let the bell take the app down: a refused or failed
                    // mark-read is not worth losing the session over.
                    .catch(() => {})
                    .finally(() => setMarkingNotificationsRead(false));
            }}
          />

          {mobileNavOpen && (
            <div className="mobile-portal-overlay" onClick={() => setMobileNavOpen(false)} />
          )}

          {/* Reuse Sidebar for Portal Continuity */}
          <aside className={`portal-sidebar ${mobileNavOpen ? 'mobile-open' : ''}`}>
            <div className="portal-sidebar-brand">
              <div>
                <div className="portal-sidebar-logo">SCALEEZY</div>
                <div className="portal-sidebar-logo-sub">THE ATELIER EXPERIENCE</div>
              </div>
              <div className="portal-sidebar-mark" aria-hidden="true">S</div>
              <button type="button" className="portal-nav-toggle" onClick={toggleNav}
                      aria-label={navCollapsed ? 'Expand navigation' : 'Collapse navigation'}
                      aria-expanded={!navCollapsed}
                      title={navCollapsed ? 'Expand navigation' : 'Collapse navigation'}>
                {navCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
              </button>
            </div>
            
            <nav className="portal-menu">
              <PortalMenu
                sections={navSections}
                activeTab={dashboardTab}
                collapsed={navCollapsed && !mobileNavOpen}
                onPick={(tab) => { setView('dashboard'); setDashboardTab(tab); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}
              />
              <NavItem icon={LogOut} label={t('nav.logout')} collapsed={navCollapsed && !mobileNavOpen}
                       onClick={() => { setShowLogoutConfirm(true); setMobileNavOpen(false); }} />
            </nav>
          </aside>

          <main className="portal-main">
            <div className="selector-container">
              <div className="selector-header">
                <h1 className="selector-title" style={{ fontFamily: 'var(--font-serif)', fontSize: '32px' }}>{t('entry.createOrderTitle', 'Create New Custom Order')}</h1>
                <p className="selector-subtitle" style={{ color: 'var(--text-secondary)' }}>{t('entry.createOrderSubtitle', 'Choose how you would like to initiate this bespoke order creation.')}</p>
              </div>

              {/* Orders already being written. Offered, never resumed
                  silently: picking one up is a decision, and so is throwing it
                  away. Shows enough to tell two apart -- who it is for, what is
                  on it, how far it got and when it was last touched. */}
              {resumableDrafts.length > 0 && (
                <div className="content-card" style={{ marginBottom: '20px' }}>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>
                    {resumableDrafts.length === 1
                      ? t('entry.orderInProgressOne', 'You have an order in progress')
                      : t('entry.orderInProgressMany', `You have ${resumableDrafts.length} orders in progress`, { count: resumableDrafts.length })}
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                    {t('entry.savedAutomaticallySub', 'Saved automatically. Pick one up where you left it, or discard it.')}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {resumableDrafts.map(draft => {
                      const garments = (draft.payload?.garments || [])
                        .map(g => g.template_key).filter(Boolean);
                      return (
                        <div key={draft.id} style={{ display: 'flex', alignItems: 'center', gap: '12px',
                                                     flexWrap: 'wrap', borderTop: '1px solid var(--border-color)',
                                                     paddingTop: '10px' }}>
                          <div style={{ flex: '1 1 260px' }}>
                            <div style={{ fontWeight: 600 }}>
                              {draft.customer_name || t('entry.unnamedCustomer', 'Unnamed customer')}
                            </div>
                            <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                              {garments.length ? garments.join(', ') : t('wizard.noGarmentChosen', 'No garment chosen yet')}
                              {' · '}{t('entry.stepXofY', `Step ${draft.current_step} of 6`, { step: draft.current_step })}
                              {' · '}{t('entry.lastSaved', 'last saved')} {new Date(draft.updated_at).toLocaleString()}
                            </div>
                          </div>
                          <button type="button" className="btn-primary" onClick={() => hydrateWizard(draft)}>
                            {t('entry.resume', 'Resume')}
                          </button>
                          {discardingDraftId === draft.id ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                              <span style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                                {t('entry.discardConfirmDesc', 'Discard this order? Nothing has been booked, but everything entered on it will be lost.')}
                              </span>
                              <button type="button" className="btn-secondary"
                                      onClick={() => setDiscardingDraftId(null)}>
                                {t('entry.keepIt', 'Keep it')}
                              </button>
                              <button type="button" className="btn-primary" disabled={deletingDraftId === draft.id} onClick={async () => {
                                if (deletingDraftId) return;
                                setDeletingDraftId(draft.id);
                                try {
                                  await api.deleteOrderDraft(draft.id);
                                  setResumableDrafts(prev => prev.filter(d => d.id !== draft.id));
                                } catch (err) {
                                  console.error('Could not discard the draft', err);
                                  alert('Could not discard that order — it is still saved.');
                                } finally {
                                  setDiscardingDraftId(null);
                                  setDeletingDraftId(null);
                                }
                              }}>
                                {deletingDraftId === draft.id
                                  ? t('common.discarding', 'Discarding…')
                                  : t('entry.discardPermanently', 'Discard permanently')}
                              </button>
                            </div>
                          ) : (
                            <button type="button" className="btn-secondary"
                                    onClick={() => setDiscardingDraftId(draft.id)}>
                              {t('entry.discard', 'Discard')}
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="selector-cards-grid">
                {/* Option 1: Existing Customer -- pointless (and confusing) until
                    the boutique actually has one, so it waits for the first. */}
                {customersList.length > 0 && (
                <div className="selector-option-card" onClick={openExistingCustomerModal}>
                  <div className="selector-option-icon">
                    <Users size={32} />
                  </div>
                  <h3 className="selector-option-title">{t('entry.existingCustomerTitle', 'Existing Customer')}</h3>
                  <p className="selector-option-desc">{t('entry.existingCustomerDesc', 'Select a client profile from your database and retrieve their measurements.')}</p>
                  
                  <div className="selector-features-list">
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>{t('entry.useSavedMeasurements', 'Use saved measurements')}</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>{t('entry.viewPastOrdersPrefs', 'View past orders & prefs')}</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>{t('entry.fasterOrderCreation', 'Faster order creation')}</span>
                    </div>
                  </div>

                  <button className="selector-card-btn">
                    {t('entry.selectExistingCustomerBtn', 'Select Existing Customer')}
                    <ArrowRight size={14} />
                  </button>
                </div>
                )}

                {/* Option 2: New Customer */}
                <div className="selector-option-card" onClick={handleStartNewCustomer}>
                  <div className="selector-option-icon">
                    <User size={32} />
                  </div>
                  <h3 className="selector-option-title">
                    {customersList.length === 0
                      ? t('entry.firstCustomerTitle', 'Create Your First Customer')
                      : t('entry.newCustomerTitle', 'New Customer')}
                  </h3>
                  <p className="selector-option-desc">{t('entry.newCustomerDesc', 'Create a new customer profile and input their measurements from scratch.')}</p>

                  <div className="selector-features-list">
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>{t('entry.addCustomerDetails', 'Add customer details')}</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>{t('entry.captureMeasurements', 'Capture measurements')}</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>{t('entry.startCustomJourney', 'Start custom journey')}</span>
                    </div>
                  </div>

                  <button className="selector-card-btn">
                    {customersList.length === 0
                      ? t('entry.firstCustomerTitle', 'Create Your First Customer')
                      : t('entry.createNewCustomerBtn', 'Create New Customer')}
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>

              {/* Explanatory Flow Diagrams at the bottom */}
              <div className="selector-flow-explain-box">
                <h4 className="selector-flow-explain-title">{t('entry.howProcessWorksTitle', 'How the creation process works')}</h4>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
                  {/* Flow with Existing Customer */}
                  <div>
                    <h5 style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '16px' }}>{t('entry.flowExistingCustomerHeader', 'FLOW WITH EXISTING CUSTOMER:')}</h5>
                    <div className="flow-steps-visual">
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><Users size={16} /></div>
                        <span className="flow-step-node-title">{t('entry.flowSelectCustomer', 'Select Customer')}</span>
                        <span className="flow-step-node-desc">{t('entry.flowSelectCustomerDesc', 'Search and select client from database')}</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><FileText size={16} /></div>
                        <span className="flow-step-node-title">{t('entry.flowReviewProfile', 'Review Profile')}</span>
                        <span className="flow-step-node-desc">{t('entry.flowReviewProfileDesc', 'Check sizes and preferences')}</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><Sparkles size={16} /></div>
                        <span className="flow-step-node-title">{t('entry.flowCreateOrder', 'Create Order')}</span>
                        <span className="flow-step-node-desc">{t('entry.flowCreateOrderDesc', 'Define styles, fabrics and details')}</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><Check size={16} /></div>
                        <span className="flow-step-node-title">{t('entry.flowProceedJourney', 'Proceed to Journey')}</span>
                        <span className="flow-step-node-desc">{t('entry.flowProceedJourneyDesc', 'Stitching and fitting commences')}</span>
                      </div>
                    </div>
                  </div>

                  {/* Flow with New Customer */}
                  <div>
                    <h5 style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '16px' }}>{t('entry.flowNewCustomerHeader', 'FLOW WITH NEW CUSTOMER:')}</h5>
                    <div className="flow-steps-visual">
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><User size={16} /></div>
                        <span className="flow-step-node-title">{t('entry.flowAddPersonalDetails', 'Add Personal Details')}</span>
                        <span className="flow-step-node-desc">{t('entry.flowAddPersonalDetailsDesc', 'Input names and contact credentials')}</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><Scissors size={16} /></div>
                        <span className="flow-step-node-title">{t('entry.flowCaptureSizes', 'Capture Sizes')}</span>
                        <span className="flow-step-node-desc">{t('entry.flowCaptureSizesDesc', 'Log exact body dimensions')}</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><Compass size={16} /></div>
                        <span className="flow-step-node-title">{t('entry.flowStylePreferences', 'Style Preferences')}</span>
                        <span className="flow-step-node-desc">{t('entry.flowStylePreferencesDesc', 'Choose fabrics, cuts, necklines')}</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><ArrowRight size={16} /></div>
                        <span className="flow-step-node-title">{t('entry.flowProceedJourney', 'Proceed to Journey')}</span>
                        <span className="flow-step-node-desc">{t('entry.flowSubmitCreationWorkflowDesc', 'Submit for creation workflow')}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </main>



          {/* Existing Customer Search Modal Overlay */}
          {showSearchModal && (
            <div className="existing-customer-search-modal">
              <div className="search-modal-card">
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '16px', fontWeight: 600 }}>{t('entry.selectExistingCustomerModalTitle', 'Select Existing Customer')}</h3>
                  <button className="close-btn" onClick={() => setShowSearchModal(false)}><X size={20} /></button>
                </div>
                
                <div className="search-input-wrapper" style={{ width: '100%' }}>
                  <Search size={18} />
                  <input 
                    type="text" 
                    placeholder={t('entry.searchCustomerPlaceholder', 'Search by customer name or mobile number...')} 
                    value={searchModalQuery}
                    onChange={(e) => setSearchModalQuery(e.target.value)}
                    className="form-control"
                    autoFocus
                  />
                </div>

                <div className="search-results-list">
                  {filteredSearchModalCustomers.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '13px' }}>
                      {t('entry.noCustomersFoundMatching', 'No customers found matching')} "{searchModalQuery}"
                    </div>
                  ) : (
                    filteredSearchModalCustomers.map(cust => (
                      <div 
                        key={cust.id} 
                        className="search-result-item"
                        onClick={() => handleSelectExistingCustomer(cust)}
                      >
                        <div>
                          <div className="search-result-name">{cust.first_name} {cust.last_name}</div>
                          <div className="search-result-phone">📞 {formatMobile(cust.mobile_number)}</div>
                        </div>
                        <span className="search-result-garment">{cust.garment_type}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 6. 5-STEP CREATION WIZARD FLOW */}
      {view === 'wizard' && (
        <div className="wizard-outer-wrapper" style={{ display: 'flex', flexDirection: 'column', width: '100%', minHeight: '100vh', backgroundColor: '#fcfcfd' }}>
          {/* Brand header & stepper */}
          <div className="wizard-header-container" style={{ borderBottom: '1px solid var(--border-color)', backgroundColor: '#fff', padding: '16px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', maxWidth: '1280px', margin: '0 auto 16px' }}>
              <div className="brand-logo" style={{ fontSize: '20px', fontWeight: 800, letterSpacing: '1px', color: 'var(--text-primary)' }}>SCALEEZY</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                {draftSaveState !== 'idle' && (
                  <span style={{ fontSize: '12.5px',
                                 color: draftSaveState === 'conflict' || draftSaveState === 'failed'
                                        ? '#c0392b' : 'var(--text-secondary)' }}>
                    {draftSaveState === 'saving' && t('wizard.saving')}
                    {draftSaveState === 'saved' && t('wizard.saved')}
                    {draftSaveState === 'failed' && t('wizard.couldNotSave')}
                    {draftSaveState === 'conflict' && t('wizard.conflict')}
                  </span>
                )}
                <span style={{ cursor: 'pointer', color: 'var(--text-secondary)' }} onClick={() => setView('dashboard')}>
                  <X size={20} />
                </span>
              </div>
            </div>
            
            {/* Stepper progress bar */}
            <div className="stepper-progress-bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', maxWidth: '1000px', margin: '0 auto', position: 'relative' }}>
              {[
                { number: 1, label: t('wizard.aiDesignStudio'), sub: t('wizard.subDiscoverDesign', 'Discover & approve design') },
                { number: 2, label: t('wizard.fabricSelection'), sub: t('wizard.subChooseFabrics', 'Choose fabrics') },
                { number: 3, label: t('wizard.personalDetails'), sub: t('wizard.reviewAndConfirm', 'review & confirm') },
                { number: 4, label: t('wizard.measurements'), sub: t('wizard.completed', 'Completed') },
                { number: 5, label: t('wizard.tailorAssignment'), sub: t('wizard.subAssignTailor', 'Assign tailor') },
                { number: 6, label: t('wizard.completeOrder'), sub: t('wizard.reviewAndConfirm', 'review & confirm') }
              ].map((step, index) => {

                const stepNum = index + 1;
                const isCompleted = currentStep > stepNum;
                const isActive = currentStep === stepNum;
                return (
                  <React.Fragment key={step.number}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', flex: 1, position: 'relative', zIndex: 2 }}>
                      <div style={{
                        width: '28px',
                        height: '28px',
                        borderRadius: '50%',
                        backgroundColor: isCompleted ? '#107c41' : (isActive ? '#0f291e' : '#f1f3f5'),
                        color: isCompleted || isActive ? '#fff' : 'var(--text-secondary)',
                        border: isActive ? '2px solid #107c41' : 'none',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '12px',
                        fontWeight: 600,
                        marginBottom: '8px'
                      }}>
                        {isCompleted ? <Check size={14} /> : step.number}
                      </div>
                      <span style={{ fontSize: '11px', fontWeight: isActive || isCompleted ? 600 : 500, color: isActive || isCompleted ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                        {step.label}
                      </span>
                      <span style={{ fontSize: '9px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                        {isActive ? t('wizard.reviewAndConfirm', 'review & confirm') : (isCompleted ? t('wizard.completed', 'Completed') : step.sub)}
                      </span>
                    </div>
                    {index < 5 && (
                      <div style={{
                        height: '2px',
                        flex: 1,
                        backgroundColor: currentStep > stepNum ? '#107c41' : '#e0e0e0',
                        margin: '0 -20px',
                        transform: 'translateY(-20px)',
                        zIndex: 1
                      }}></div>
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
          <div className="main-content" style={{ padding: '40px 24px 100px', maxWidth: '1280px', margin: '0 auto', width: '100%' }}>
            <div className="workspace-panel">
            {/* STEP 3: Personal Details */}
            {currentStep === 3 && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">{t('wizard.createCustomerTitle', 'Create Customer')}</h1>
                  <p className="page-subtitle">{t('wizard.createCustomerSubtitle', 'Onboard new clients into the Scaleezy ecosystem. Capture style preferences and measurements for a personalized atelier experience.')}</p>
                </div>

                <div className="content-card">
                  <div className="card-title">
                    <Users size={20} />
                    {t('wizard.customerProfile', 'Customer Profile')}
                  </div>

                  <div className="profile-upload-widget">
                    <div className="photo-preview-placeholder" onClick={() => document.getElementById('profile-picker').click()}>
                      {profilePhotoPreview ? (
                        <img src={profilePhotoPreview} alt="Preview" />
                      ) : (
                        <Upload size={24} />
                      )}
                    </div>
                    <div className="photo-upload-actions">
                      <label className="upload-btn-label">
                        📷 {t('common.takePhoto', 'Take photo')}
                        <input
                          type="file"
                          id="profile-picker-camera"
                          accept="image/*"
                          capture="environment"
                          style={{ display: 'none' }}
                          onChange={handleProfilePhotoChange}
                        />
                      </label>
                      <label className="upload-btn-label">
                        {t('common.chooseFromGallery', 'Choose from gallery')}
                        <input
                          type="file"
                          id="profile-picker"
                          accept="image/*"
                          style={{ display: 'none' }}
                          onChange={handleProfilePhotoChange}
                        />
                      </label>
                      <span className="upload-btn-sub">{t('wizard.uploadPhotoSub', 'JPG, PNG up to 5MB')}</span>
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">{t('wizard.firstName', 'First Name')} <span className="required">*</span></label>
                      <input 
                        type="text" 
                        value={customerForm.first_name}
                        onChange={(e) => setCustomerForm({...customerForm, first_name: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. Amara"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('wizard.lastName', 'Last Name')} <span className="required">*</span></label>
                      <input 
                        type="text" 
                        value={customerForm.last_name}
                        onChange={(e) => setCustomerForm({...customerForm, last_name: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. Singh"
                      />
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">{t('wizard.mobileNumber', 'Mobile Number')} <span className="required">*</span></label>
                      <div className="input-wrapper">
                        <span className="input-icon-left" style={{ fontSize: '14px', left: '12px' }}>🇮🇳 +91</span>
                        <input 
                          type="tel" 
                          value={customerForm.mobile_number}
                          onChange={(e) => setCustomerForm({...customerForm, mobile_number: e.target.value})}
                          style={{ paddingLeft: '65px' }}
                          placeholder="98765 43210"
                        />
                      </div>
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('wizard.emailAddress', 'Email Address')} <span className="required">*</span></label>
                      <input 
                        type="email" 
                        value={customerForm.email_address || ''}
                        onChange={(e) => setCustomerForm({...customerForm, email_address: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. amara.s@example.com"
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">{t('wizard.address', 'Address')} <span className="required">*</span></label>
                    <input 
                      type="text" 
                      value={customerForm.address || ''}
                      onChange={(e) => setCustomerForm({...customerForm, address: e.target.value})}
                      className="form-control" 
                      placeholder={t('wizard.addressPlaceholder', 'Street name, Apartment, City, State, PIN code')}
                    />
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">{t('wizard.cityRegion', 'City / Region')}</label>
                      <input 
                        type="text" 
                        value={customerForm.city_region || ''}
                        onChange={(e) => setCustomerForm({...customerForm, city_region: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. New Delhi"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('wizard.source', 'Source')}</label>
                      <select 
                        value={customerForm.source}
                        onChange={(e) => setCustomerForm({...customerForm, source: e.target.value})}
                        className="form-control"
                      >
                        <option value="Walk In">{t('wizard.walkIn', 'Walk In')}</option>
                        <option value="Instagram">{t('wizard.instagram', 'Instagram')}</option>
                        <option value="Referral">{t('wizard.referral', 'Referral')}</option>
                        <option value="Website">{t('wizard.website', 'Website')}</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">{t('wizard.customerType', 'Customer Type')}</label>
                      <select 
                        value={customerForm.customer_type}
                        onChange={(e) => setCustomerForm({...customerForm, customer_type: e.target.value})}
                        className="form-control"
                      >
                        <option value="Women">{t('wizard.women', 'Women')}</option>
                        <option value="Men">{t('wizard.men', 'Men')}</option>
                        <option value="Kids">{t('wizard.kids', 'Kids')}</option>
                      </select>
                    </div>
                  </div>

                  {/* Dresses on this order.

                      The garment list, the options in it and the fields each
                      garment needs all come from /api/catalog/templates/. This
                      replaced a hardcoded seven-item dropdown and a stitch-parts
                      map that had to be edited in four places to add a garment.

                      An order holds several dresses -- a lehenga, its blouse and
                      a dupatta are three -- so this is a multiple choice, and
                      each one opens its own form in the next step. */}
                  <DressesDropdown
                    title={t('wizard.dressesInOrder', 'Dresses in this Order')}
                    subtitle={t('wizard.dressesInOrderSub', 'Pick every garment being stitched. Each one gets its own measurements and options.')}
                    isRequired={true}
                    garmentTemplates={garmentTemplates}
                    garmentJobs={garmentJobs}
                    addingGarmentKey={addingGarmentKey}
                    garmentTemplatesError={garmentTemplatesError}
                    loadGarmentTemplates={loadGarmentTemplates}
                    addGarment={addGarment}
                    removeGarment={removeGarment}
                  />

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">{t('wizard.patternStyle', 'Pattern Style')}</label>
                      <select 
                        value={customerForm.pattern_style || ''}
                        onChange={(e) => setCustomerForm({...customerForm, pattern_style: e.target.value})}
                        className="form-control"
                      >
                        <option value="">{t('wizard.selectPatternStyle', 'Select Pattern Style')}</option>
                        <option value="Floral Prints">{t('wizard.floralPrints', 'Floral Prints')}</option>
                        <option value="Traditional Brocade">{t('wizard.traditionalBrocade', 'Traditional Brocade')}</option>
                        <option value="Solid Plain">{t('wizard.solidPlain', 'Solid Plain')}</option>
                        <option value="Geometrical">{t('wizard.geometrical', 'Geometrical')}</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('wizard.occasion', 'Occasion')}</label>
                      <select 
                        value={customerForm.occasion || ''}
                        onChange={(e) => setCustomerForm({...customerForm, occasion: e.target.value})}
                        className="form-control"
                      >
                        <option value="">{t('wizard.selectOccasion', 'Select Occasion')}</option>
                        <option value="Wedding / Bridal">{t('wizard.weddingBridal', 'Wedding / Bridal')}</option>
                        <option value="Festive wear">{t('wizard.festiveWear', 'Festive wear')}</option>
                        <option value="Formal Event">{t('wizard.formalEvent', 'Formal Event')}</option>
                        <option value="Casual wear">{t('wizard.casualWear', 'Casual wear')}</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">{t('wizard.customRequirements', 'Custom Requirements')}</label>
                    <textarea 
                      value={customerForm.custom_requirements || ''}
                      onChange={(e) => setCustomerForm({...customerForm, custom_requirements: e.target.value})}
                      className="form-control"
                      placeholder={t('wizard.customReqPlaceholder', 'Specify custom preferences (e.g. padding, side zippers, extra margin)')}
                    />
                  </div>
                </div>

                {/* Additional Information Card */}
                <div className="content-card">
                  <div className="card-title">
                    <FolderOpen size={20} />
                    {t('wizard.additionalInformation', 'Additional Information')}
                  </div>

                  <div className="form-grid-3">
                    <div className="form-group">
                      <label className="form-label">{t('wizard.dateOfBirth', 'Date of Birth')}</label>
                      <input 
                        type="date" 
                        value={customerForm.date_of_birth || ''}
                        onChange={(e) => setCustomerForm({...customerForm, date_of_birth: e.target.value})}
                        className="form-control"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('wizard.occupation', 'Occupation')}</label>
                      <input 
                        type="text" 
                        value={customerForm.occupation || ''}
                        onChange={(e) => setCustomerForm({...customerForm, occupation: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. Entrepreneur"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('wizard.preferredCommunication', 'Preferred Communication')}</label>
                      <select 
                        value={customerForm.preferred_communication}
                        onChange={(e) => setCustomerForm({...customerForm, preferred_communication: e.target.value})}
                        className="form-control"
                      >
                        <option value="WhatsApp">WhatsApp</option>
                        <option value="Call">{t('wizard.phoneCall', 'Phone Call')}</option>
                        <option value="Email">Email</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">{t('wizard.notes', 'Notes')}</label>
                    <textarea 
                      value={customerForm.notes || ''}
                      onChange={(e) => setCustomerForm({...customerForm, notes: e.target.value})}
                      className="form-control"
                      placeholder={t('wizard.customerNotesPlaceholder', 'Any additional notes about the customer...')}
                    />
                  </div>
                </div>
              </>
            )}

            {/* STEP 4: Measurements */}
            {currentStep === 4 && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">Garment Details</h1>
                  <p className="page-subtitle">Measurements, style options and materials for every dress on this order. Each garment asks only for what it actually needs.</p>
                </div>

                {garmentJobs.length === 0 && (
                  <div className="content-card">
                    <div style={{ fontSize: '13.5px', color: 'var(--text-secondary)' }}>
                      No garment was chosen in the previous step, so there is nothing to
                      measure yet. Go back and pick at least one dress.
                    </div>
                  </div>
                )}

                {/* One card per dress. Which fields appear -- and which are
                    required -- is decided by the template's rules, so a corset
                    asks about boning and a churidar asks for the calf, without
                    either question existing in this file. */}
                {garmentJobs.map(job => (
                  <div className="content-card" key={job.key}>
                    <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Scissors size={20} /> {job.template.name}
                      </span>
                      <button
                        type="button"
                        className="btn-secondary"
                        style={{ padding: '4px 10px', fontSize: '12px' }}
                        onClick={() => removeGarment(job.key)}
                      >
                        <Trash2 size={12} /> Remove
                      </button>
                    </div>

                    <MaterialsNeeded templateId={job.template.id} />
                    {['basic', 'measurements', 'style', 'materials', 'production'].map(sectionKey => {
                      const section = job.template.sections.find(s => s.key === sectionKey);
                      if (!section) return null;
                      return (
                        <div key={sectionKey} style={{ marginBottom: '20px' }}>
                          <div style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-secondary)', margin: '4px 0 12px' }}>
                            {section.title}
                          </div>
                          <TemplateForm
                            template={job.template}
                            section={sectionKey}
                            values={job.values}
                            errors={garmentErrors[job.key] || {}}
                            onChange={values => updateGarmentValues(job.key, values)}
                            quantities={job.quantities || {}}
                            quantityErrors={garmentQuantityErrors[job.key] || {}}
                            onQuantityChange={(fieldKey, quantity) =>
                              updateGarmentQuantity(job.key, fieldKey, quantity)}
                            sources={job.sources || {}}
                            brought={job.brought || {}}
                            defaultSource={defaultMaterialSource(job)}
                            onSourceChange={(fieldKey, source) =>
                              updateGarmentSource(job.key, fieldKey, source)}
                            onBroughtChange={(fieldKey, entry) =>
                              updateGarmentBrought(job.key, fieldKey, entry)}
                            /* null when Inventory is gated off: TemplateForm
                               already drops its whole "Set up inventory"
                               banner when this is missing, which is what we
                               want -- offering the button navigated to a tab
                               the sidebar no longer has, so it left the wizard
                               for the dashboard and then sat on whatever tab
                               was already showing. */
                            onGoToInventory={canSeeTab(currentUser, 'inventory')
                              ? () => { setView('dashboard'); setDashboardTab('inventory'); }
                              : null}
                          />
                        </div>
                      );
                    })}
                  </div>
                ))}
              </>
            )}

            {/* STEP 1: AI Design Studio */}
            {currentStep === 1 && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">Design Studio</h1>
                  <p className="page-subtitle">Designs matched to this client's measurements, occasion, budget and order history — searched across your catalogue, past orders and saved library, and ranked with the reason for every suggestion.</p>
                </div>

                <div className="content-card">
                  <div className="tabs-header">
                    <button
                      className={`tab-btn ${designSourceTab === 'studio' ? 'active' : ''}`}
                      onClick={() => setDesignSourceTab('studio')}
                    >
                      <Sparkles size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
                      Design Studio
                    </button>
                    <button
                      className={`tab-btn ${designSourceTab === 'references' ? 'active' : ''}`}
                      onClick={() => setDesignSourceTab('references')}
                    >
                      <Upload size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
                      My References
                    </button>
                  </div>

                  {designSourceTab === 'studio' && (
                    <Suspense fallback={<ScreenLoading />}>
                      {/* Garment Selector on Step 1 */}
                      <DressesDropdown
                        title={t('wizard.dressesInOrder', 'Dresses in this Order')}
                        subtitle="Pick every garment being stitched. Each one opens its own design parts below."
                        garmentTemplates={garmentTemplates}
                        garmentJobs={garmentJobs}
                        addingGarmentKey={addingGarmentKey}
                        garmentTemplatesError={garmentTemplatesError}
                        loadGarmentTemplates={loadGarmentTemplates}
                        addGarment={addGarment}
                        removeGarment={removeGarment}
                      />

                      {garmentJobs.length === 0 ? (
                        <p style={{ color: 'var(--text-secondary)', padding: '20px 0' }}>
                          Select a garment above to browse its designs, part by part.
                        </p>
                      ) : garmentJobs.map(job => (
                        <div key={job.key} style={{ marginBottom: '20px' }}>
                          {/* One picker per dress, each reading its own
                              garment's parts. Selections are kept per garment
                              so a saree's pallu and a blouse's neck never share
                              a slot. */}
                          <GarmentPartPicker
                            garmentKey={job.template?.key || job.key}
                            garmentName={job.template?.name || job.key}
                            selection={partSelection[job.key] || {}}
                            onChange={(next) => handlePartSelection(job.key, next)}
                          />
                        </div>
                      ))}

                      {/* Everything chosen so far, garment by garment. A choice
                          made under Saree scrolls out of sight as soon as the
                          customer opens Blouse, so the whole outfit is
                          gathered here at the foot of the screen. */}
                      <SelectedDesignSummary
                        garmentJobs={garmentJobs}
                        onClear={(garmentKey, part) => {
                          const next = { ...(partSelection[garmentKey] || {}) };
                          delete next[part];
                          handlePartSelection(garmentKey, next);
                        }}
                      />
                    </Suspense>
                  )}

                  {designSourceTab === 'references' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                      <DressesDropdown
                        title={t('wizard.dressesInOrder', 'Dresses in this Order')}
                        subtitle="Pick every garment being stitched. Each one opens its own design parts below."
                        garmentTemplates={garmentTemplates}
                        garmentJobs={garmentJobs}
                        addingGarmentKey={addingGarmentKey}
                        garmentTemplatesError={garmentTemplatesError}
                        loadGarmentTemplates={loadGarmentTemplates}
                        addGarment={addGarment}
                        removeGarment={removeGarment}
                      />

                      {/* A reference per PART of each dress: this pallu, that
                          border. Same component, same {part: reference} slot and
                          same garment parts the Design Studio tab uses -- with
                          the catalogue half switched off, because here the
                          customer is giving a reference rather than picking one. */}
                      {garmentJobs.length === 0 ? (
                        <p style={{ color: 'var(--text-secondary)', padding: '4px 0' }}>
                          Select a garment above to add a reference for each of its parts.
                        </p>
                      ) : (
                        // Its own boundary: the picker is lazy, and this branch
                        // sits outside the one the Design Studio tab renders in.
                        <Suspense fallback={<ScreenLoading />}>
                          {garmentJobs.map(job => (
                            <GarmentPartPicker
                              key={job.key}
                              ownOnly
                              garmentKey={job.template?.key || job.key}
                              garmentName={job.template?.name || job.key}
                              references={partReferences[job.key] || {}}
                              onReferencesChange={(next) => handlePartReferences(job.key, next)}
                            />
                          ))}
                        </Suspense>
                      )}

                      {/* The flat whole-order reference box that used to sit
                          here is gone: the part tabs above ask the same two
                          questions -- a picture, or a link -- against the part
                          of the garment each one is actually about, which is
                          what the workroom needs to know. `designSource` and
                          `designLinks` are still carried on the draft, so
                          nothing downstream of it changes. */}
                    </div>
                  )}
                </div>
              </>
            )}

            {/* STEP 2: Fabric Selection */}
            {currentStep === 2 && !selectionReviewPhase && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">Fabric Selection</h1>
                  <p className="page-subtitle">Choose the perfect fabric that brings the design to life. Browse from your uploaded fabrics or explore premium boutique inventory.</p>
                </div>

                <div className="content-card">
                  <div className="tabs-header">
                    <button 
                      className={`tab-btn ${fabricTab === 'boutique' ? 'active' : ''}`}
                      onClick={() => setFabricTab('boutique')}
                    >
                      Boutique Fabrics
                    </button>
                    <button 
                      className={`tab-btn ${fabricTab === 'my-fabric' ? 'active' : ''}`}
                      onClick={() => setFabricTab('my-fabric')}
                    >
                      Customer Fabrics (My Fabrics)
                    </button>
                    <button 
                      className={`tab-btn ${fabricTab === 'accessories' ? 'active' : ''}`}
                      onClick={() => setFabricTab('accessories')}
                    >
                      Accessories
                    </button>
                  </div>

                  {fabricTab === 'my-fabric' ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                      {/* Part-wise reference photos & links for each garment */}
                      {garmentJobs.length > 0 && (
                        <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                          <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>
                            Part-wise Fabric References &amp; Links
                          </div>
                          {garmentJobs.map(job => (
                            <GarmentPartPicker
                              key={job.key}
                              garmentKey={job.template?.key || job.key}
                              garmentName={job.template?.name || job.key}
                              ownOnly
                              isFabric
                              taxonomy={fabricTaxonomy}
                              references={partReferences[job.key] || {}}
                              onReferencesChange={(next) => handlePartReferences(job.key, next)}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  ) : fabricTab === 'accessories' ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                      {/* Sub-tabs header for Accessories */}
                      <div style={{ display: 'flex', gap: '10px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
                        <button
                          type="button"
                          className={`btn-secondary ${accessorySubTab === 'boutique' ? 'btn-primary' : ''}`}
                          style={{ padding: '6px 16px', fontSize: '12.5px', borderRadius: '20px', fontWeight: 600 }}
                          onClick={() => setAccessorySubTab('boutique')}
                        >
                          Boutique Accessories
                        </button>
                        <button
                          type="button"
                          className={`btn-secondary ${accessorySubTab === 'customer' ? 'btn-primary' : ''}`}
                          style={{ padding: '6px 16px', fontSize: '12.5px', borderRadius: '20px', fontWeight: 600 }}
                          onClick={() => setAccessorySubTab('customer')}
                        >
                          Customer Accessories (My Accessories)
                        </button>
                      </div>

                      {accessorySubTab === 'boutique' ? (
                        /* Garment Accessories & Trims Selection (Boutique Inventory) */
                        garmentJobs.length > 0 && (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                            <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>
                              Boutique Accessories &amp; Trims
                            </div>
                            <Suspense fallback={<ScreenLoading />}>
                              <GarmentFabricPicker
                                garmentJobs={garmentJobs}
                                fabrics={fabrics}
                                taxonomy={fabricTaxonomy}
                                selection={fabricSelection}
                                onChange={handleFabricSelection}
                                accessoriesOnly
                              />
                            </Suspense>
                          </div>
                        )
                      ) : (
                        /* Customer Accessories & References */
                        garmentJobs.length > 0 && (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                            <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>
                              Customer Provided Accessories &amp; References
                            </div>
                            {garmentJobs.map(job => (
                              <GarmentPartPicker
                                key={job.key}
                                garmentKey={job.template?.key || job.key}
                                garmentName={job.template?.name || job.key}
                                ownOnly
                                isFabric
                                accessoriesOnly
                                taxonomy={fabricTaxonomy}
                                references={partReferences[job.key] || {}}
                                onReferencesChange={(next) => handlePartReferences(job.key, next)}
                              />
                            ))}
                          </div>
                        )
                      )}
                    </div>
                  ) : (
                    <div>

                      {/* An empty library is now the ordinary day-one state:
                          new boutiques are no longer seeded with five fabrics
                          at another business's prices, so this grid rendered as
                          a blank rectangle with no explanation and no way
                          forward. The wizard's tailor step already handles its
                          own empty case this way. Both routes out are offered,
                          because using the customer's own cloth is a normal
                          boutique workflow, not a fallback. */}
                      {fabrics.filter(f => f.is_available !== false).length === 0 && (
                        <div style={{ padding: '24px', border: '1px dashed var(--border-color)', borderRadius: '10px', textAlign: 'center', display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center' }}>
                          {/* Two empty states, not one. An empty library is a
                              job the owner can go and do; a library the
                              platform has switched off is not, and the grid
                              looks identically empty either way. Offering "Save
                              & add fabrics" in the second case saved the draft,
                              left the wizard, and landed on whatever tab was
                              already showing -- the Fabrics tab it asked for is
                              gone from the nav, so the derived dashboardTab
                              refuses it. Say so instead, and leave the one
                              route that still works. */}
                          <div style={{ fontWeight: 600 }}>
                            {canSeeTab(currentUser, 'fabrics') ? 'Your fabric library is empty' : 'Fabric library unavailable'}
                          </div>
                          <div style={{ color: 'var(--text-secondary)', fontSize: '13px', maxWidth: '46ch', lineHeight: 1.5 }}>
                            {canSeeTab(currentUser, 'fabrics') ? (<>
                              Add the rolls you stock to pick from them here — or switch to
                              <strong> Customer's Own Fabric</strong> above if the client is bringing their own.
                            </>) : (<>
                              The fabric library is switched off for this boutique, so there is
                              nothing to pick from. Switch to
                              <strong> Customer's Own Fabric</strong> above to carry on with this order.
                            </>)}
                          </div>
                          {/* Save first, then go. This button is the product's
                              own advice to a boutique with no fabric library --
                              and following it used to destroy the order being
                              written, because the wizard's only copy was in
                              this component's state. The draft is on the server
                              before we navigate, so the work is waiting when
                              they come back. */}
                          {canSeeTab(currentUser, 'fabrics') && (
                          <button type="button" className="btn-secondary" disabled={draftSaveState === 'saving'} onClick={async () => {
                            try {
                              await persistDraft({ step: 4 });
                            } catch (err) {
                              alert('Could not save this order before opening the fabric library. '
                                    + 'Nothing has been lost — try again.');
                              return;
                            }
                            setView('dashboard');
                            setDashboardTab('fabrics');
                          }}>
                            {draftSaveState === 'saving' ? 'Saving…' : <>Save &amp; add fabrics</>}
                          </button>
                          )}
                        </div>
                      )}

                      {/* Garment by garment, part by part. FabricPlacement
                          already records which garment/section/slot each roll
                          suits and Manage Fabrics already edits that, so this
                          lays the boutique's own filing out rather than
                          offering one common list for every dress. */}
                      <Suspense fallback={<ScreenLoading />}>
                        <FabricColorFilter
                          fabrics={fabrics}
                          value={fabricColorQuery}
                          onChange={setFabricColorQuery}
                        />
                        <GarmentFabricPicker
                          garmentJobs={garmentJobs}
                          fabrics={colourFilteredFabrics}
                          taxonomy={fabricTaxonomy}
                          selection={fabricSelection}
                          onChange={handleFabricSelection}
                        />
                      </Suspense>
                      </div>
                    )}
                  </div>

                {/* AI Draping Trigger Section */}
                {selectedFabric && (
                  <div style={{
                    marginTop: '24px',
                    padding: '16px 20px',
                    background: 'rgba(212, 175, 55, 0.05)',
                    border: '1px dashed rgba(212, 175, 55, 0.3)',
                    borderRadius: '8px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <Sparkles size={20} style={{ color: 'var(--accent-text, #b07c40)' }} />
                      <div style={{ textAlign: 'left' }}>
                        <span style={{ fontSize: '13px', fontWeight: 600, color: '#fff', display: 'block' }}>Scaleezy Live Visualizer Available</span>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Drape the selected {selectedFabric.name} fabric onto the chosen style sketch to preview it.</span>
                      </div>
                    </div>
                    <button 
                      type="button" 
                      className="btn-primary" 
                      style={{ padding: '8px 16px', fontSize: '12px', background: 'linear-gradient(135deg, #d35400, #e67e22)', border: 'none', cursor: 'pointer' }}
                      onClick={() => setShowDrapingModal(true)}
                    >
                      Try On / Drape Fabric
                    </button>
                  </div>
                )}
              </>
            )}

            {/* STEP 2, second phase: everything chosen, dress by dress, read
                back before the customer's details are asked for. Reads the
                same garment jobs the two steps before it wrote. */}
            {currentStep === 2 && selectionReviewPhase && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">Review &amp; Confirm</h1>
                  <p className="page-subtitle">Designs, fabrics and accessories for every garment in this order. Edit any of them and come back — nothing chosen is lost.</p>
                </div>

                <div className="accent-banner" style={{ margin: '4px 0 16px', backgroundColor: '#e2f5ec', borderColor: '#c3ebdb', color: '#107c41', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Check size={16} />
                  <span>Check each garment below, then Confirm &amp; Continue to add the customer's details.</span>
                </div>

                <div className="content-card">
                  <GarmentSelectionsReview
                    jobs={garmentJobs}
                    fabrics={fabrics}
                    taxonomy={fabricTaxonomy}
                    onEditDesigns={() => { setSelectionReviewPhase(false); setCurrentStep(1); }}
                    onEditFabrics={() => setSelectionReviewPhase(false)}
                  />
                </div>
              </>
            )}

            {/* STEP 5: Tailor Assignment & Pricing Review */}
            {currentStep === 5 && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">{t('wizard.reviewStaffAssignmentTitle', 'Review & Staff Assignment')}</h1>
                  <p className="page-subtitle">{t('wizard.reviewStaffAssignmentDesc', 'Assign a Master Tailor to supervise/cut and a Stitching Tailor for the assembly.')}</p>
                </div>

                <div className="responsive-profile-grid" style={{ gap: '24px' }}>
                  {/* Master Assignment Card */}
                  <div className="content-card" style={{ margin: 0 }}>
                    <div className="card-title">
                      <Scissors size={20} style={{ color: 'var(--accent-text, #b07c40)' }} />
                      {t('wizard.assignMasterTailorTitle', '1. Assign Master Tailor (Cutting & Supervision)')}
                    </div>
                    <div className="tailors-list" style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {tailors.filter(t => t.role === 'Master').length === 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '8px 0' }}>
                          <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>{t('wizard.noMasterTailorsAvailable', 'No Master Tailors available. Add one to continue:')}</div>
                          <button 
                            className="btn-primary" 
                            style={{ alignSelf: 'flex-start', padding: '8px 16px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
                            onClick={() => setDashboardTab('staff')}
                          >
                            <Plus size={14} /> {t('wizard.addMasterTailorBtn', 'Add Master Tailor')}
                          </button>
                        </div>
                      ) : (
                        tailors.filter(t => t.role === 'Master').map(tailorItem => (
                          <div 
                            key={tailorItem.id} 
                            className={`tailor-row ${selectedMaster?.id === tailorItem.id ? 'selected' : ''}`}
                            onClick={() => setSelectedMaster(tailorItem)}
                            style={{
                              display: 'flex',
                              gap: '16px',
                              alignItems: 'center',
                              padding: '12px',
                              borderRadius: '8px',
                              border: selectedMaster?.id === tailorItem.id ? '2px solid var(--accent-text, #b07c40)' : '1px solid var(--border-color)',
                              background: selectedMaster?.id === tailorItem.id ? 'rgba(212, 175, 55, 0.05)' : 'transparent',
                              cursor: 'pointer'
                            }}
                          >
                            <div style={{ width: '40px', height: '40px', borderRadius: '50%', overflow: 'hidden', flexShrink: 0 }}>
                              <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(tailorItem.name)}`} alt={tailorItem.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            </div>
                            <div className="tailor-info" style={{ flex: 1 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>{tailorItem.name}</span>
                                <span className={`order-row-badge ${tailorItem.status === 'Available' ? 'confirmed' : 'in_progress'}`} style={{ fontSize: '10px', padding: '1px 6px' }}>
                                  {tailorItem.status === 'Available' ? t('wizard.available', 'Available') : t('wizard.busy', 'Busy')}
                                </span>
                              </div>
                              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{tailorItem.specialty}</span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Tailor Assignment Card */}
                  <div className="content-card" style={{ margin: 0 }}>
                    <div className="card-title">
                      <Scissors size={20} />
                      {t('wizard.assignStitchingTailorTitle', '2. Assign Stitching Tailor (Sewing & Details)')}
                    </div>
                    <div className="tailors-list" style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {stitchingStaff().length === 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '8px 0' }}>
                          <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>{t('wizard.noStitchingTailorsAvailable', 'No Stitching Tailors available. Add one to continue:')}</div>
                          <button 
                            className="btn-primary" 
                            style={{ alignSelf: 'flex-start', padding: '8px 16px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
                            onClick={() => setDashboardTab('staff')}
                          >
                            <Plus size={14} /> {t('wizard.addStitchingTailorBtn', 'Add Stitching Tailor')}
                          </button>
                        </div>
                      ) : (
                        stitchingStaff().map(tailorItem => (
                          <div 
                            key={tailorItem.id} 
                            className={`tailor-row ${selectedTailor?.id === tailorItem.id ? 'selected' : ''}`}
                            onClick={() => setSelectedTailor(tailorItem)}
                            style={{
                              display: 'flex',
                              gap: '16px',
                              alignItems: 'center',
                              padding: '12px',
                              borderRadius: '8px',
                              border: selectedTailor?.id === tailorItem.id ? '2px solid var(--border-color)' : '1px solid var(--border-color)',
                              background: selectedTailor?.id === tailorItem.id ? 'rgba(0, 0, 0, 0.03)' : 'transparent',
                              cursor: 'pointer'
                            }}
                          >
                            <div style={{ width: '40px', height: '40px', borderRadius: '50%', overflow: 'hidden', flexShrink: 0 }}>
                              <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(tailorItem.name)}`} alt={tailorItem.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            </div>
                            <div className="tailor-info" style={{ flex: 1 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>{tailorItem.name}</span>
                                <span className={`order-row-badge ${tailorItem.status === 'Available' ? 'confirmed' : 'in_progress'}`} style={{ fontSize: '10px', padding: '1px 6px' }}>
                                  {tailorItem.status === 'Available' ? t('wizard.available', 'Available') : t('wizard.busy', 'Busy')}
                                </span>
                              </div>
                              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{tailorItem.specialty}</span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>

                {/* Delivery Method Configuration Card */}
                <div className="content-card" style={{ margin: '24px 0 0 0' }}>
                  <div className="card-title">
                    <Compass size={20} style={{ color: 'var(--accent-text, #b07c40)' }} />
                    {t('wizard.deliveryMethodConfigTitle', '3. Delivery Method Configuration')}
                  </div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                    <div style={{ display: 'flex', gap: '24px' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>
                        <input 
                          type="radio" 
                          name="deliveryMethod" 
                          value="Direct Pickup"
                          checked={deliveryMethod === 'Direct Pickup'}
                          onChange={() => setDeliveryMethod('Direct Pickup')}
                        />
                        {t('wizard.directBoutiquePickup', 'Direct Boutique Pickup')}
                      </label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>
                        <input 
                          type="radio" 
                          name="deliveryMethod" 
                          value="Courier"
                          checked={deliveryMethod === 'Courier'}
                          onChange={() => setDeliveryMethod('Courier')}
                        />
                        {t('wizard.courierDeliveryOption', 'Courier Delivery')}
                      </label>
                    </div>

                    {deliveryMethod === 'Courier' && (
                      <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', background: 'rgba(0,0,0,0.02)', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-color)', marginTop: '8px' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('wizard.courierServiceProvider', 'Courier Service Provider')}</label>
                          <input 
                            type="text" 
                            className="form-control"
                            placeholder="e.g. DHL, Blue Dart, FedEx"
                            value={courierService}
                            onChange={(e) => setCourierService(e.target.value)}
                            required
                          />
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('wizard.trackingReferenceNumber', 'Tracking Reference Number')}</label>
                          <input 
                            type="text" 
                            className="form-control"
                            placeholder="e.g. 123456789"
                            value={trackingNumber}
                            onChange={(e) => setTrackingNumber(e.target.value)}
                          />
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', gridColumn: 'span 2' }}>
                          <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('wizard.shippingDeliveryAddress', 'Shipping / Delivery Address')}</label>
                          <textarea 
                            className="form-control"
                            rows="3"
                            placeholder="Enter detailed delivery address..."
                            value={deliveryAddress}
                            onChange={(e) => setDeliveryAddress(e.target.value)}
                            required
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}

            {/* STEP 6: Review & Complete Order / Payment */}
            {currentStep === 6 && (
              <>
                {/* Shown when creating the order failed outright -- the one
                    failure that wrote nothing, and so the one where trying
                    again is safe. Everything after that point lands on the
                    confirmation screen instead, because going back is what
                    creates a second order. */}
                {wizardError && (
                  <div role="alert" style={{ margin: '4px 0 16px', background: '#fdf2f2', border: '1px solid #f5c6c6', color: '#8a2020', borderRadius: '8px', padding: '12px 14px', fontSize: '13.5px', display: 'flex', justifyContent: 'space-between', gap: '12px', whiteSpace: 'pre-wrap' }}>
                    <span>{wizardError}</span>
                    <button type="button" onClick={() => setWizardError(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontWeight: 700 }}>Dismiss</button>
                  </div>
                )}
                {!paymentPhase ? (
                  // Review & Complete Order Phase (Mockup 1)
                  <>
                    <div className="page-title-group">
                      <h1 className="page-title">Review & Complete Order</h1>
                      <p className="page-subtitle">Review the selections and order details. Once confirmed, it goes to the tailor and the customer is kept updated at every step.</p>
                    </div>

                    <div className="accent-banner" style={{ margin: '4px 0 16px', backgroundColor: '#e2f5ec', borderColor: '#c3ebdb', color: '#107c41', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Check size={16} />
                      <span>All set — ready to create this order.</span>
                    </div>

                    {/* Section 1: Order Summary */}
                    <div className="content-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <div className="card-title" style={{ margin: 0 }}>
                          <FileText size={20} />
                          1. Order Summary
                        </div>
                        <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => setCurrentStep(3)}>
                          Edit
                        </button>
                      </div>

                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          {selectedDesignTemplates.length > 0 ? (
                            <img src={selectedDesignTemplates[0]} alt="Garment" style={{ width: '48px', height: '48px', borderRadius: '6px', objectFit: 'cover', border: '1px solid var(--border-color)' }} />
                          ) : designPreviews.length > 0 ? (
                            <img src={designPreviews[0]} alt="Garment" style={{ width: '48px', height: '48px', borderRadius: '6px', objectFit: 'cover', border: '1px solid var(--border-color)' }} />
                          ) : (
                            <div style={{ width: '48px', height: '48px', borderRadius: '6px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><ShoppingBag size={20} /></div>
                          )}
                          <div>
                            <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>
                              {garmentJobs.length > 1 ? `GARMENTS (${garmentJobs.length})` : 'GARMENT'}
                            </span>
                            {/* Every dress on the order, not just the first --
                                a lehenga with its blouse and dupatta is three. */}
                            <span style={{ fontSize: '13px', fontWeight: 600 }}>
                              {customerForm.customer_type} • {garmentJobs.length
                                ? wizardGarmentLabel
                                : customerForm.garment_type}
                            </span>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          {fabricTab === 'boutique' && selectedFabric ? (
                            <>
                              <div style={{ width: '48px', height: '48px', borderRadius: '6px', backgroundColor: '#f1f3f5', overflow: 'hidden', border: '1px solid var(--border-color)' }}>
                                <img src={resolveMediaUrl(selectedFabric.image_url)} alt="Fabric" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                              </div>
                              <div>
                                <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>FABRIC</span>
                                <span style={{ fontSize: '13px', fontWeight: 600 }}>{selectedFabric.name}</span>
                              </div>
                            </>
                          ) : fabricPreviews.length > 0 ? (
                            <>
                              <div style={{ width: '48px', height: '48px', borderRadius: '6px', overflow: 'hidden', border: '1px solid var(--border-color)' }}>
                                <img src={fabricPreviews[0]} alt="Fabric" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                              </div>
                              <div>
                                <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>FABRIC</span>
                                <span style={{ fontSize: '13px', fontWeight: 600 }}>Uploaded Fabric</span>
                              </div>
                            </>
                          ) : (
                            <>
                              <div style={{ width: '48px', height: '48px', borderRadius: '6px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--border-color)' }}><Upload size={20} /></div>
                              <div>
                                <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>FABRIC</span>
                                <span style={{ fontSize: '13px', fontWeight: 600 }}>Customer Fabric</span>
                              </div>
                            </>
                          )}
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div style={{ width: '32px', height: '32px', borderRadius: '50%', border: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <span style={{ width: '20px', height: '20px', borderRadius: '50%', backgroundColor: getColorCircleStyle(selectedFabric?.color || 'Custom') }}></span>
                          </div>
                          <div>
                            <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>COLOR</span>
                            <span style={{ fontSize: '13px', fontWeight: 600 }}>{selectedFabric ? selectedFabric.color : 'Custom'}</span>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div style={{ width: '48px', height: '48px', borderRadius: '6px', backgroundColor: '#0f291e', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff' }}>
                            <Sparkles size={20} />
                          </div>
                          <div>
                            <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>WORK/EMBROIDERY</span>
                            <span style={{ fontSize: '13px', fontWeight: 600 }}>{customerForm.embellishments || 'Zari & Thread'}</span>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div>
                            <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)', display: 'block', fontWeight: 600 }}>OCCASION</span>
                            <span style={{ fontSize: '13px', fontWeight: 600 }}>{customerForm.occasion || 'Wedding'}</span>
                          </div>
                        </div>
                      </div>

                      {(customerForm.neckline_style || customerForm.sleeve_style || customerForm.back_style || customerForm.silhouette || customerForm.pattern_style) && (
                        <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px dashed var(--border-color)' }}>
                          <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', fontWeight: 600, textTransform: 'uppercase', marginBottom: '8px' }}>Style Specifications</span>
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '12px' }}>
                            {customerForm.neckline_style && (
                              <div>
                                <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block' }}>Neckline</span>
                                <span style={{ fontSize: '11px', fontWeight: 600 }}>{customerForm.neckline_style}</span>
                              </div>
                            )}
                            {customerForm.sleeve_style && (
                              <div>
                                <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block' }}>Sleeves</span>
                                <span style={{ fontSize: '11px', fontWeight: 600 }}>{customerForm.sleeve_style}</span>
                              </div>
                            )}
                            {customerForm.back_style && (
                              <div>
                                <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block' }}>Back Style</span>
                                <span style={{ fontSize: '11px', fontWeight: 600 }}>{customerForm.back_style}</span>
                              </div>
                            )}
                            {customerForm.silhouette && (
                              <div>
                                <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block' }}>Silhouette</span>
                                <span style={{ fontSize: '11px', fontWeight: 600 }}>{customerForm.silhouette}</span>
                              </div>
                            )}
                            {customerForm.pattern_style && (
                              <div>
                                <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block' }}>Pattern</span>
                                <span style={{ fontSize: '11px', fontWeight: 600 }}>{customerForm.pattern_style}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Section 2: Garment details.
                        Previously a decorative card showing a measurement count
                        and a hardcoded "98% accuracy". It never showed a single
                        thing the staff had actually typed, so the review step
                        could not be used to check the order. */}
                    <div className="content-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <div className="card-title" style={{ margin: 0 }}>
                          <Scissors size={20} />
                          2. Garment Details
                        </div>
                        <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => setCurrentStep(2)}>
                          Edit
                        </button>
                      </div>

                      <GarmentSummary jobs={garmentJobs} onEdit={() => setCurrentStep(2)} />
                    </div>

                    {/* Section 3: Tailor Details */}
                    <div className="content-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <div className="card-title" style={{ margin: 0 }}>
                          <User size={20} />
                          3. Tailor Details
                        </div>
                        <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => setCurrentStep(5)}>
                          Edit
                        </button>
                      </div>

                      {selectedTailor ? (
                        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '20px', rowGap: '12px', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                          <div style={{ width: '48px', height: '48px', borderRadius: '50%', overflow: 'hidden', flexShrink: 0 }}>
                            <img src={getTailorAvatarUrl(selectedTailor.name)} alt={selectedTailor.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          </div>
                          <div style={{ flex: 1, minWidth: '150px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span style={{ fontSize: '15px', fontWeight: 600 }}>{selectedTailor.name}</span>
                              <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#107c41', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '8px' }}><Check size={8} /></span>
                            </div>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'block' }}>{selectedTailor.specialty} • 12+ Years Experience</span>
                            <div style={{ display: 'flex', gap: '6px', marginTop: '6px', flexWrap: 'wrap' }}>
                              {getTailorTags(selectedTailor.name).map((tag, idx) => (
                                <span key={idx} style={{ fontSize: '9px', backgroundColor: '#f1f3f5', padding: '2px 6px', borderRadius: '4px', color: 'var(--text-secondary)' }}>{tag}</span>
                              ))}
                              <span style={{ fontSize: '9px', backgroundColor: '#f1f3f5', padding: '2px 6px', borderRadius: '4px', color: 'var(--text-secondary)' }}>+2</span>
                            </div>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <span style={{ fontSize: '13px', fontWeight: 700, display: 'block' }}>98%</span>
                            <span style={{ fontSize: '9px', color: 'var(--text-secondary)' }}>ON-TIME DELIVERY</span>
                          </div>
                          <div style={{ width: '1px', height: '32px', backgroundColor: 'var(--border-color)' }}></div>
                          <div style={{ textAlign: 'right' }}>
                            <span style={{ fontSize: '13px', fontWeight: 700, display: 'block' }}>1200+</span>
                            <span style={{ fontSize: '9px', color: 'var(--text-secondary)' }}>ORDERS DONE</span>
                          </div>
                          <div style={{ width: '1px', height: '32px', backgroundColor: 'var(--border-color)' }}></div>
                          <div style={{ textAlign: 'right' }}>
                            <span style={{ fontSize: '13px', fontWeight: 700, display: 'block' }}>5 km</span>
                            <span style={{ fontSize: '9px', color: 'var(--text-secondary)' }}>FROM BOUTIQUE</span>
                          </div>
                        </div>
                      ) : (
                        <div style={{ padding: '16px', textAlign: 'center', border: '1px dashed var(--border-color)', borderRadius: '8px', color: 'var(--text-secondary)' }}>
                          No tailor assigned. Go back to Step 5 to assign a tailor.
                        </div>
                      )}
                    </div>

                    {/* Section 4: Delivery Details */}
                    <div className="content-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <div className="card-title" style={{ margin: 0 }}>
                          <ShoppingBag size={20} />
                          4. Delivery Details
                        </div>
                        <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => setCurrentStep(1)}>
                          Edit
                        </button>
                      </div>

                      <div className="delivery-details-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
                        <div>
                          <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block', fontWeight: 600, textTransform: 'uppercase', marginBottom: '6px' }}>DELIVERY ADDRESS</span>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <MapPin size={16} style={{ color: 'var(--text-secondary)', flexShrink: 0, marginTop: '2px' }} />
                            <div>
                              <span style={{ fontSize: '12px', fontWeight: 600, display: 'block' }}>{customerForm.first_name} {customerForm.last_name}</span>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', lineHeight: 1.4 }}>{customerForm.address || 'B-32, Green Park Extension, New Delhi - 110016, India'}</span>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginTop: '4px' }}>📞 {formatMobile(customerForm.mobile_number)}</span>
                            </div>
                          </div>
                        </div>

                        <div>
                          <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block', fontWeight: 600, textTransform: 'uppercase', marginBottom: '6px' }}>DELIVERY METHOD</span>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <ShoppingBag size={16} style={{ color: 'var(--text-secondary)', flexShrink: 0, marginTop: '2px' }} />
                            <div>
                              <span style={{ fontSize: '12px', fontWeight: 600, display: 'block' }}>Standard Delivery</span>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>Estimated delivery by</span>
                              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginTop: '2px' }}>
                                {new Date(Date.now() + 15 * 24 * 60 * 60 * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div>
                          <span style={{ fontSize: '9px', color: 'var(--text-secondary)', display: 'block', fontWeight: 600, textTransform: 'uppercase', marginBottom: '6px' }}>COMMUNICATION</span>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <MessageSquare size={16} style={{ color: '#107c41', flexShrink: 0, marginTop: '2px' }} />
                            <div>
                              <span style={{ fontSize: '12px', fontWeight: 600, display: 'block' }}>WhatsApp</span>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>{formatMobile(customerForm.mobile_number)}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Section 5: Special Instructions */}
                    <div className="content-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <div className="card-title" style={{ margin: 0 }}>
                          <MessageSquare size={20} />
                          Add Special Instructions (Optional)
                        </div>
                        <Edit2 size={16} style={{ color: 'var(--text-secondary)' }} />
                      </div>
                      <textarea
                        value={specialInstructions}
                        onChange={(e) => setSpecialInstructions(e.target.value)}
                        className="form-control"
                        placeholder="e.g. Prefer hand embroidery on dupatta, avoid bright colors, etc."
                        style={{ minHeight: '80px', fontSize: '12px' }}
                      />
                    </div>

                    {/* Step 6 Review Buttons */}
                    <div className="step6-action-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '20px', borderTop: '1px solid var(--border-color)', paddingTop: '20px' }}>
                      <button className="btn-secondary" onClick={handleBack}>
                        <ArrowLeft size={16} /> Back: Tailor Assignment
                      </button>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <button className="btn-secondary" onClick={handleSaveDraft} disabled={ctaBusy}>
                          Save as Draft
                        </button>
                        <button className="btn-primary" onClick={handleNext} disabled={ctaBusy} style={{ opacity: ctaBusy ? 0.6 : 1 }}>
                          {ctaBusy ? 'Working…' : <>Create Order & Pay <ArrowRight size={16} /></>}
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  // Create Order & Continue / Payment Options Phase (Mockup 2)
                  <>
                    <div className="page-title-group">
                      <h1 className="page-title">Create Order & Continue</h1>
                      <p className="page-subtitle">Record how the customer is paying: in full now, or part now and the rest after the design is completed.</p>
                    </div>

                    <div className="accent-banner" style={{ margin: '4px 0 16px', backgroundColor: '#e2f5ec', borderColor: '#c3ebdb', color: '#107c41', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <ShieldCheck size={16} />
                      <span>Order and payment details are stored securely with Scaleezy.</span>
                    </div>

                    {/* Order Review Summary Row */}
                    <div className="content-card">
                      <h3 style={{ fontSize: '13px', fontWeight: 700, marginBottom: '16px' }}>1. Order Review</h3>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', alignItems: 'center', gap: '20px' }}>
                        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', alignItems: 'center' }}>
                          {selectedDesignTemplates.length > 0 ? (
                            <img src={selectedDesignTemplates[0]} alt="Garment" style={{ width: '48px', height: '48px', borderRadius: '6px', objectFit: 'cover' }} />
                          ) : designPreviews.length > 0 ? (
                            <img src={designPreviews[0]} alt="Garment" style={{ width: '48px', height: '48px', borderRadius: '6px', objectFit: 'cover' }} />
                          ) : (
                            <div style={{ width: '48px', height: '48px', borderRadius: '6px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><ShoppingBag size={20} /></div>
                          )}
                          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
                            <div>
                              <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Garment</span>
                              {/* wizardGarmentLabel, not customerForm.garment_type: the customer
                                  field holds one value and follows whichever dress was picked
                                  first, so a blouse-and-lehenga order named a single garment on
                                  the one screen where the money is taken. The two sidebars below
                                  already read the helper; this was the call site it missed. */}
                              <span style={{ fontSize: '12px', fontWeight: 600 }}>{customerForm.customer_type} • {wizardGarmentLabel}</span>
                            </div>
                            <div>
                              <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Fabric</span>
                              <span style={{ fontSize: '12px', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                {fabricTab === 'boutique' && selectedFabric ? (
                                  <>
                                    {selectedFabric.name}
                                    <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: getColorCircleStyle(selectedFabric.color), display: 'inline-block' }}></span>
                                    {selectedFabric.color}
                                  </>
                                ) : fabricPreviews.length > 0 ? (
                                  'Uploaded Fabric'
                                ) : (
                                  'Customer Fabric'
                                )}
                              </span>
                            </div>
                            <div>
                              <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Work / Embroidery</span>
                              <span style={{ fontSize: '12px', fontWeight: 600 }}>{customerForm.embellishments || 'Zari & Thread'}</span>
                            </div>
                            <div>
                              <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Tailor</span>
                              <span style={{ fontSize: '12px', fontWeight: 600 }}>{selectedTailor?.name || 'Rohit Mehra'}</span>
                            </div>
                          </div>
                        </div>

                        <button className="btn-secondary" style={{ fontSize: '11px', padding: '6px 12px' }} onClick={() => setPaymentPhase(false)}>
                          View Full Summary
                        </button>
                      </div>
                    </div>

                    {/* Payment Options Section */}
                    <div className="content-card">
                      <h3 style={{ fontSize: '13px', fontWeight: 700, marginBottom: '16px' }}>2. Payment Options</h3>
                      <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '16px' }}>Choose how the customer is paying for this order.</p>

                      <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        {/* Option 1: Full Payment */}
                        <div 
                          onClick={() => setPaymentOption('full')}
                          style={{
                            border: `2px solid ${paymentOption === 'full' ? '#0f291e' : 'var(--border-color)'}`,
                            borderRadius: '8px',
                            padding: '20px',
                            cursor: 'pointer',
                            backgroundColor: paymentOption === 'full' ? '#fcfdfd' : '#fff',
                            position: 'relative'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                            <div>
                              <span style={{ fontSize: '13px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
                                Pay Now (Full Payment)
                                <span style={{ fontSize: '9px', backgroundColor: '#e2f5ec', color: '#107c41', padding: '2px 6px', borderRadius: '4px' }}>Recommended</span>
                              </span>
                              <p style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '4px' }}>Pay the full amount now and we'll start your design & creation immediately.</p>
                            </div>
                            <div style={{ width: '16px', height: '16px', borderRadius: '50%', border: '2px solid #0f291e', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              {paymentOption === 'full' && <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#0f291e' }}></div>}
                            </div>
                          </div>
                          
                          <span style={{ fontSize: '20px', fontWeight: 800, display: 'block', color: 'var(--text-primary)', marginBottom: '16px' }}>
                            {formatMoney(getTotalPrice())}
                          </span>

                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px', color: 'var(--text-secondary)' }}>
                              <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#e2f5ec', color: '#107c41', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px' }}><Check size={8} /></span>
                              Priority design & production
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px', color: 'var(--text-secondary)' }}>
                              <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#e2f5ec', color: '#107c41', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px' }}><Check size={8} /></span>
                              Faster delivery
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px', color: 'var(--text-secondary)' }}>
                              <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#e2f5ec', color: '#107c41', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px' }}><Check size={8} /></span>
                              Full peace of mind
                            </div>
                          </div>
                        </div>

                        {/* Option 2: Partial Payment */}
                        <div 
                          onClick={() => setPaymentOption('partial')}
                          style={{
                            border: `2px solid ${paymentOption === 'partial' ? '#0f291e' : 'var(--border-color)'}`,
                            borderRadius: '8px',
                            padding: '20px',
                            cursor: 'pointer',
                            backgroundColor: paymentOption === 'partial' ? '#fcfdfd' : '#fff',
                            position: 'relative'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                            <div>
                              <span style={{ fontSize: '13px', fontWeight: 700 }}>Pay Partially Now</span>
                              <p style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '4px' }}>Take part payment now to confirm the order. The rest is due after the design is completed.</p>
                            </div>
                            <div style={{ width: '16px', height: '16px', borderRadius: '50%', border: '2px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              {paymentOption === 'partial' && <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#0f291e' }}></div>}
                            </div>
                          </div>

                          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px', marginBottom: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <div>
                                <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Pay Advance (Custom Amount)</span>
                                <input 
                                  type="number"
                                  className="form-control"
                                  style={{ padding: '6px', fontSize: '14px', width: '150px', marginTop: '4px' }}
                                  placeholder={`e.g. ${(getTotalPrice() / 2).toFixed(0)}`}
                                  value={advancePaymentAmount || ''}
                                  onChange={(e) => setAdvancePaymentAmount(parseFloat(e.target.value) || 0)}
                                  onClick={(e) => e.stopPropagation()}
                                />
                              </div>
                              <span style={{ fontSize: '8px', backgroundColor: '#f1f3f5', color: 'var(--text-secondary)', padding: '2px 4px', borderRadius: '2px' }}>Non-refundable</span>
                            </div>
                          </div>

                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                              <span style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block' }}>Remaining Balance Due at Delivery</span>
                              {/* Must agree with what is actually sent above.
                                  Showing the half here while sending the half
                                  there made the two consistent and both wrong;
                                  showing the half here while sending zero would
                                  be worse, because the preview is the number
                                  the owner reads back to the customer. */}
                              <span style={{ fontSize: '16px', fontWeight: 700 }}>{formatMoney(Math.max(0, getTotalPrice() - (Number(advancePaymentAmount) || 0)))}</span>
                            </div>
                            <span style={{ fontSize: '8px', backgroundColor: '#e2f5ec', color: '#107c41', padding: '2px 4px', borderRadius: '2px', fontWeight: 600 }}>DUE AT DELIVERY</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* What happens next banner */}
                    <div style={{ display: 'flex', gap: '12px', padding: '16px', backgroundColor: '#fcfdfd', border: '1px solid var(--border-color)', borderRadius: '8px', alignItems: 'center' }}>
                      <Calendar size={20} style={{ color: 'var(--text-secondary)' }} />
                      <div>
                        <h5 style={{ fontSize: '11px', fontWeight: 600 }}>What happens next?</h5>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>We'll create initial design concepts and share with you within 2–3 business days. Once you approve the final design, we'll share the remaining payment link (if applicable) and begin crafting your garment.</p>
                      </div>
                    </div>

                    {/* Terms Checkbox */}
                    <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontSize: '11px', color: 'var(--text-secondary)', marginTop: '10px' }}>
                      <input 
                        type="checkbox" 
                        checked={agreedToTerms} 
                        onChange={(e) => setAgreedToTerms(e.target.checked)}
                        style={{ cursor: 'pointer' }}
                      />
                      <span>I agree to the <span style={{ textDecoration: 'underline' }}>Terms & Conditions</span> and <span style={{ textDecoration: 'underline' }}>Privacy Policy</span>.</span>
                    </label>

                    {/* Step 6 Payment Buttons */}
                    <div className="step6-action-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '20px', borderTop: '1px solid var(--border-color)', paddingTop: '20px' }}>
                      <button className="btn-secondary" onClick={handleBack}>
                        <ArrowLeft size={16} /> Back: Tailor Assignment
                      </button>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <button className="btn-secondary" onClick={handleSaveDraft} disabled={ctaBusy}>
                          Save as Draft
                        </button>
                        <button className="btn-primary" onClick={handleNext} disabled={!agreedToTerms || ctaBusy} style={{ opacity: (agreedToTerms && !ctaBusy) ? 1 : 0.6 }}>
                          {ctaBusy ? 'Placing the order…' : <>Confirm Order & Continue <ArrowRight size={16} /></>}
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </>
            )}
          </div>

          {/* Right Sidebar */}
          <div className="sidebar-panel">
            {currentStep < 5 ? (
              <>
                <div className="sidebar-card">
                  <div className="sidebar-card-title">
                    <Sparkles size={16} />
                    {t('wizard.howItWorks', 'How it works')}
                  </div>
                  <div className="instruction-steps">
                    <div className="instruction-step">
                      <div className="step-num-badge">1</div>
                      <div className="instruction-step-content">
                        <span className="instruction-step-title">{t('wizard.enterProfileDetails', 'Enter Profile Details')}</span>
                        <span className="instruction-step-desc">{t('wizard.provideSizeTagsDesc', 'Provide size tags and contact channels.')}</span>
                      </div>
                    </div>
                    <div className="instruction-step">
                      <div className="step-num-badge">2</div>
                      <div className="instruction-step-content">
                        <span className="instruction-step-title">{t('wizard.submitMeasurements', 'Submit Measurements')}</span>
                        <span className="instruction-step-desc">{t('wizard.collectBodySpecsDesc', 'Collect 7 key body specifications.')}</span>
                      </div>
                    </div>
                    <div className="instruction-step">
                      <div className="step-num-badge">3</div>
                      <div className="instruction-step-content">
                        <span className="instruction-step-title">{t('wizard.bespokeDesignFabric', 'Bespoke Design & Fabric')}</span>
                        <span className="instruction-step-desc">{t('wizard.pickRefSketchesDesc', 'Pick reference sketches and fabric rolls.')}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="sidebar-card">
                  <div className="sidebar-card-title">
                    <ShieldCheck size={16} />
                    {t('wizard.privacyAssured', 'Privacy Assured')}
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {t('wizard.privacyAssuredDesc', 'Customer details, style files, and measurement records are saved exclusively to the Scaleezy database cluster and never shared.')}
                  </p>
                </div>
              </>
            ) : currentStep === 5 ? (
              <div className="sidebar-card">
                <div className="sidebar-card-title">
                  <ShoppingBag size={18} />
                  {t('wizard.orderSummaryTitle', 'Order Summary')}
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px' }}>
                  <div style={{ fontSize: '14px', fontWeight: 600 }}>{customerForm.customer_type} • {wizardGarmentLabel}</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                    {t('wizard.fabricLabel', 'Fabric:')} {fabricTab === 'boutique' && selectedFabric ? `${selectedFabric.name} (${selectedFabric.color})` : t('wizard.customerFabricLabel', 'Customer fabric')}
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {/* One line per dress: each garment's own subtotal, because
                      each garment carries its own price now. */}
                  {garmentJobs.map(job => (
                    <div className="summary-item-row" key={job.key}>
                      <span>{job.template?.name || job.key}</span>
                      <span className="price-display">{formatMoney(jobSubtotal(job))}</span>
                    </div>
                  ))}
                  <div className="summary-item-row">
                    <span>{t('wizard.packagingHandling', 'Packaging & Handling')}</span>
                    <span className="price-display">{formatMoney(quotePrices.packaging)}</span>
                  </div>
                  {parseFloat(quotePrices.discount || 0) > 0 && (
                    <div className="summary-item-row">
                      <span>{t('wizard.discount', 'Discount')}</span>
                      <span className="price-display">−{formatMoney(quotePrices.discount)}</span>
                    </div>
                  )}
                  <div className="summary-item-row" style={{ borderTop: '1px solid #f1f3f5', paddingTop: '10px' }}>
                    <span>{t('wizard.subtotal', 'Subtotal')}</span>
                    <span className="price-display">{formatMoney(getSubtotal())}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>{t('wizard.taxesGst', 'Taxes (GST 5%)')}</span>
                    <span className="price-display">{formatMoney(getTaxes())}</span>
                  </div>
                  <div className="summary-item-row total">
                    <span>{t('wizard.totalAmount', 'Total Amount')}</span>
                    <span className="price-display total">{formatMoney(getTotalPrice())}</span>
                  </div>
                </div>
              </div>
            ) : (
              // Order Summary/Breakdown for Step 6 (Review & Payment)
              <>
                <div className="sidebar-card">
                  <div className="sidebar-card-title">
                    <ShoppingBag size={18} />
                    {paymentPhase ? 'Order Summary' : 'Order Cost Breakdown'}
                  </div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px' }}>
                    {/* Name every dress. The breakdown below still prices the
                        first one only -- see the base-price row. */}
                    <div style={{ fontSize: '14px', fontWeight: 600 }}>
                      {customerForm.customer_type} • {wizardGarmentLabel}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                      Fabric: {fabricTab === 'boutique' && selectedFabric ? `${selectedFabric.name} (${selectedFabric.color})` : 'Customer fabric'}
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px', marginTop: '16px' }}>
                    {/* Each dress prices itself. Editable until the payment
                        phase, per garment, because "which dress is this money
                        for" is the question the flat model could not answer. */}
                    {garmentJobs.map(job => (
                      <div key={job.key} style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingBottom: '10px', borderBottom: '1px dashed var(--border-color)' }}>
                        <div className="summary-item-row" style={{ fontWeight: 600 }}>
                          <span>{job.template?.name || job.key}</span>
                          <span className="price-display">{formatMoney(jobSubtotal(job))}</span>
                        </div>
                        {PRICING_FIELDS.map(([field, label]) => (
                          <div className="summary-item-row" style={{ alignItems: 'center', paddingLeft: '10px' }} key={field}>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{label}</span>
                            {paymentPhase ? (
                              <span className="price-display">{formatMoney(job.pricing?.[field])}</span>
                            ) : (
                              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                                <input
                                  type="number"
                                  value={job.pricing?.[field] ?? 0}
                                  onChange={(e) => setJobPrice(job.key, field, e.target.value)}
                                  style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                                />
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    ))}
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Packaging & Handling</span>
                      {paymentPhase ? (
                        <span className="price-display">{formatMoney(quotePrices.packaging)}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input
                            type="number"
                            value={quotePrices.packaging}
                            onChange={(e) => setQuotePrices({...quotePrices, packaging: e.target.value})}
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Discount (whole order)</span>
                      {paymentPhase ? (
                        <span className="price-display">−{formatMoney(quotePrices.discount)}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input
                            type="number"
                            value={quotePrices.discount}
                            onChange={(e) => setQuotePrices({...quotePrices, discount: e.target.value})}
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '16px' }}>
                    <div className="summary-item-row" style={{ fontWeight: 600 }}>
                      <span>Subtotal</span>
                      <span className="price-display">{formatMoney(getSubtotal())}</span>
                    </div>
                    <div className="summary-item-row">
                      <span>Taxes (GST 5%)</span>
                      <span className="price-display">{formatMoney(getTaxes())}</span>
                    </div>
                    <div className="summary-item-row total" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '12px' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        Total Amount <HelpCircle size={12} style={{ color: 'var(--text-secondary)' }} />
                      </span>
                      <span className="price-display total" style={{ color: '#107c41', fontSize: '20px', fontWeight: 700 }}>
                        {formatMoney(getTotalPrice())}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="sidebar-card" style={{ display: 'flex', gap: '12px', alignItems: 'center', backgroundColor: '#fcfdfd', borderColor: '#e2e8f0' }}>
                  <ShieldCheck size={20} style={{ color: '#107c41', flexShrink: 0 }} />
                  <div>
                    <h5 style={{ fontSize: '12px', fontWeight: 600 }}>Secure Payments</h5>
                    <p style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>Your payment details are safe with us.</p>
                    <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                      <span style={{ fontSize: '8px', fontWeight: 700, color: '#1a1f36', backgroundColor: '#eaecef', padding: '2px 4px', borderRadius: '2px', letterSpacing: '0.5px' }}>VISA</span>
                      <span style={{ fontSize: '8px', fontWeight: 700, color: '#f79e1b', backgroundColor: '#eaecef', padding: '2px 4px', borderRadius: '2px', letterSpacing: '0.5px' }}>MC</span>
                      <span style={{ fontSize: '8px', fontWeight: 700, color: '#0070d2', backgroundColor: '#eaecef', padding: '2px 4px', borderRadius: '2px', letterSpacing: '0.5px' }}>AMEX</span>
                      <span style={{ fontSize: '8px', fontWeight: 700, color: '#003087', backgroundColor: '#eaecef', padding: '2px 4px', borderRadius: '2px', letterSpacing: '0.5px' }}>RUPAY</span>
                    </div>
                  </div>
                </div>

                {!paymentPhase ? (
                  <div className="sidebar-card">
                    <h5 style={{ fontSize: '13px', fontWeight: 600, marginBottom: '16px' }}>What happens next?</h5>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <div style={{ width: '24px', height: '24px', borderRadius: '4px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><Check size={12} /></div>
                        <div>
                          <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Order Confirmation</h6>
                          <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>You'll receive confirmation on WhatsApp & Email.</p>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <div style={{ width: '24px', height: '24px', borderRadius: '4px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><User size={12} /></div>
                        <div>
                          <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Tailor Notified</h6>
                          <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>We'll share details with {selectedTailor?.name || 'Rohit Mehra'} to start the magic.</p>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '12px' }}>
                        <div style={{ width: '24px', height: '24px', borderRadius: '4px', backgroundColor: '#f1f3f5', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><Scissors size={12} /></div>
                        <div>
                          <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Design & Creation</h6>
                          <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Your garment will be crafted with care and regular updates.</p>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="sidebar-card">
                    <h5 style={{ fontSize: '13px', fontWeight: 600, marginBottom: '16px' }}>Why choose Scaleezy?</h5>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div>
                        <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Trusted Tailors</h6>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Verified & experienced professionals</p>
                      </div>
                      <div>
                        <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Premium Quality</h6>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Finest fabrics and craftsmanship</p>
                      </div>
                      <div>
                        <h6 style={{ fontSize: '11px', fontWeight: 600 }}>On-time Delivery</h6>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>We value your time</p>
                      </div>
                      <div>
                        <h6 style={{ fontSize: '11px', fontWeight: 600 }}>Personalized Support</h6>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>We're here for you at every step</p>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
      )}

      {/* CONFIRMED VIEW */}
      {view === 'confirmed' && confirmedOrder && (() => {
        // The order carries the name it was saved under; the form is the
        // fallback for the moment before it is re-read.
        const confirmedCustomerName = (
          confirmedOrder.customer_name
          || `${customerForm.first_name || ''} ${customerForm.last_name || ''}`.trim()
          || 'the customer');
        return (
        <div className="order-confirmed-container">
          <div className="success-badge-container">
            <div className="success-circle"><Check size={40} /></div>
            {/* The owner or a master places this order at the counter, with
                the customer standing in front of them or not there at all.
                Addressed to "you", the screen thanked the boutique for its own
                order and named the customer as the reader. It names the
                customer as the customer instead. */}
            <h1 className="success-title">
              {t('confirmed.title', 'Order created for {name} 🎉', { name: confirmedCustomerName })}
            </h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '15px' }}>
              {t('confirmed.subtitle',
                 'It is with the workroom now, and sits on {name}\'s profile with everything recorded here.',
                 { name: confirmedCustomerName })}
            </p>
            <div className="order-id-badge">
              <span>Order ID: <strong>{orderRef(confirmedOrder)}</strong></span>
              <button 
                aria-label="Copy order ID"
                title="Copy order ID"
                style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)', minWidth: '44px', minHeight: '44px', margin: '-12px' }}
                onClick={() => {
                  navigator.clipboard.writeText(orderRef(confirmedOrder));
                  alert("Copied!");
                }}
              >
                <Copy size={16} />
              </button>
            </div>
          </div>

          <div className="order-meta-info-grid">
            <div className="meta-info-block">
              <span className="meta-info-label">Order Date</span>
              <span className="meta-info-val">
                {fmtDate(confirmedOrder.order_date)}
              </span>
            </div>
            <div className="meta-info-block">
              <span className="meta-info-label">Payment Status</span>
              {/* Was the literal `Paid • ₹{total_amount}` in success green,
                  referencing neither payment_status nor amount_paid -- so the
                  screen staff turn to face the customer announced the order
                  settled in full the moment it was placed, and contradicted the
                  invoice one click later. total_amount also arrives as a string
                  (COERCE_DECIMAL_TO_STRING is unset), and String.toLocaleString
                  does no grouping, so it printed ₹51502.50 rather than
                  ₹51,502.50. parseFloat fixes the second half. */}
              <span className="meta-info-val" style={{ color: confirmedOrder.payment_status === 'Paid' ? 'var(--success-color)' : 'var(--text-primary)' }}>
                {confirmedOrder.payment_status} • {formatMoney(confirmedOrder.amount_paid)}
                {confirmedOrder.payment_status !== 'Paid' && (
                  <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>
                    {' '}of {formatMoney(confirmedOrder.total_amount)}
                  </span>
                )}
              </span>
            </div>
            <div className="meta-info-block">
              <span className="meta-info-label">Estimated Delivery</span>
              <span className="meta-info-val">
                {fmtDate(confirmedOrder.estimated_delivery)}
              </span>
            </div>
          </div>

          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600 }}>What happens next?</h3>
            <div className="timeline-tracker">
              <div className="timeline-line"></div>
              {[
                { label: 'Stylist Review', desc: 'A stylist is reviewing the order details.', active: true, completed: true },
                { label: 'Design & Creation', desc: 'Artisans will cut and assemble the garment.', active: false, completed: false },
                { label: 'Quality Check', desc: 'Multi-level measurement and stitching validation.', active: false, completed: false },
                { label: 'Packed & Shipped', desc: 'Packed securely and handed over to the customer.', active: false, completed: false }
              ].map((node, i) => (
                <div key={i} className={`timeline-node ${node.completed ? 'completed' : ''} ${node.active ? 'active' : ''}`}>
                  <div className="timeline-node-circle">
                    {node.completed ? <Check size={14} /> : (i + 1)}
                  </div>
                  <span className="timeline-node-label">{node.label}</span>
                  <span className="timeline-node-desc">{node.desc}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="whatsapp-action-card">
            <div className="whatsapp-info">
              <span className="whatsapp-title">Crafting something just for you ✨</span>
              <span className="whatsapp-desc">Need changes or have questions? Chat directly with us on WhatsApp.</span>
            </div>
            <button className="whatsapp-btn" onClick={() => window.open(waLink(customerForm.mobile_number))}>
              <MessageSquare size={18} />
              Chat on WhatsApp
            </button>
          </div>

          {/* `flex: 1` alone does not shrink a button below its own text, so at
              390px these two ran off both edges of the screen -- the last two
              controls of the whole order flow, on a screen that then scrolled
              sideways. Wrapping, with a width floor, stacks them instead. */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', justifyContent: 'center', width: '100%', maxWidth: '450px' }}>
            <button className="btn-secondary" style={{ flex: '1 1 180px', justifyContent: 'center' }} onClick={() => { setView('dashboard'); fetchDashboardAndConfig(); }}>
              Back to Dashboard
            </button>
            <button className="btn-primary" style={{ flex: '1 1 180px', justifyContent: 'center', backgroundColor: '#0f291e' }} onClick={() => setShowInvoiceModal(true)}>
              <FileText size={18} /> View & Print Invoice
            </button>
          </div>
        </div>
        );
      })()}

      {/* Footer Navigation Bar (Only in Wizard View) */}
      {view === 'wizard' && currentStep < 6 && (
        <div className="footer-actions-bar">
          <div className="footer-left-actions">
            <button className="btn-secondary" onClick={handleBack}>
              <ArrowLeft size={16} />
              {t('common.back', 'Back')}
            </button>
          </div>
          <div className="footer-right-actions">
            {/* Show Save as Draft only if they are creating a new customer profile (Step 1 or 2) */}
            {currentStep < 3 && (
              <button className="btn-secondary" onClick={handleSaveDraft} disabled={ctaBusy}>
                {t('wizard.saveAsDraft', 'Save as Draft')}
              </button>
            )}
            <button className="btn-primary" onClick={handleNext} disabled={ctaBusy} style={{ opacity: ctaBusy ? 0.6 : 1 }}>
              {ctaBusy ? t('wizard.working', 'Working…') : <>{currentStep === 5 ? t('wizard.confirmOrder', 'Confirm Order') : (currentStep === 2 && selectionReviewPhase ? 'Confirm & Continue' : t('common.next', 'Next'))}<ArrowRight size={16} /></>}
            </button>
          </div>
        </div>
      )}

      {/* INVOICE MODAL */}
      {showInvoiceModal && confirmedOrder && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000,
          padding: '20px'
        }}>
          <div className="invoice-modal-content" style={{
            backgroundColor: '#fff',
            borderRadius: '12px',
            width: '100%',
            maxWidth: '700px',
            maxHeight: '90vh',
            overflowY: 'auto',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
            display: 'flex',
            flexDirection: 'column'
          }}>
            {/* Modal Header */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '16px 24px',
              borderBottom: '1px solid var(--border-color)'
            }} className="no-print">
              <h3 style={{ fontSize: '16px', fontWeight: 700 }}>Customer Invoice</h3>
              <button 
                aria-label="Close invoice"
                onClick={() => setShowInvoiceModal(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Invoice Printable Area */}
            <div id="invoice-printable" style={{ padding: '40px', color: '#1a1f36', fontSize: '13px', lineHeight: 1.5 }}>
              {/* Styling for printing */}
              <style>{`
                @media print {
                  body * {
                    visibility: hidden;
                  }
                    visibility: visible;
                  }
                    position: absolute;
                    left: 0;
                    top: 0;
                    width: 100%;
                    padding: 0;
                  }
                  .no-print {
                    display: none !important;
                  }
                }
              `}</style>

              <InvoiceRenderer
                template={confirmedOrder.invoice_template || boutiqueSettings?.invoice_template || 'classic'}
                data={normalizeInvoiceData(confirmedOrder, boutiqueSettings, currentUser)}
              />
            </div>

            {/* Modal Footer Controls */}
            <div style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '12px',
              padding: '16px 24px',
              borderTop: '1px solid var(--border-color)',
              backgroundColor: '#fafbfc',
              borderBottomLeftRadius: '12px',
              borderBottomRightRadius: '12px'
            }} className="no-print">
              <button 
                className="btn-secondary" 
                onClick={() => setShowInvoiceModal(false)}
              >
                Close
              </button>
              <button 
                className="btn-primary" 
                style={{ backgroundColor: '#0f291e' }}
                onClick={() => window.print()}
              >
                Print Invoice
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Notifications Drawer */}
      {showNotificationsDrawer && (
        <div style={{
          position: 'fixed',
          top: 0,
          right: 0,
          width: '400px',
          height: '100%',
          backgroundColor: 'var(--surface-color)',
          borderLeft: '1px solid var(--border-color)',
          boxShadow: '-4px 0 24px rgba(0,0,0,0.15)',
          zIndex: 1000,
          display: 'flex',
          flexDirection: 'column'
        }}>
          {/* Header */}
          <div style={{
            padding: '20px',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Bell size={20} style={{ color: 'var(--accent-text, #b07c40)' }} />
              <h3 style={{ fontSize: '18px', fontWeight: 600, margin: 0, fontFamily: 'var(--font-serif)' }}>Atelier Alerts</h3>
            </div>
            <button 
              className="btn-secondary" 
              style={{ padding: '4px 10px', fontSize: '12px' }}
              onClick={() => setShowNotificationsDrawer(false)}
            >
              Close
            </button>
          </div>

          {/* List */}
          <div style={{
            flex: 1,
            overflowY: 'auto',
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px'
          }}>
            {notifications.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)', fontSize: '13px' }}>
                No notifications received yet.
              </div>
            ) : (
              notifications.map(n => (
                <div key={n.id} style={{
                  padding: '16px',
                  backgroundColor: n.is_read ? 'rgba(0,0,0,0.01)' : 'rgba(212,175,55,0.04)',
                  border: `1px solid ${n.is_read ? 'var(--border-color)' : 'rgba(212,175,55,0.2)'}`,
                  borderRadius: '8px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 700, fontSize: '13px', color: 'var(--text-primary)' }}>{n.title}</span>
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.4 }}>{n.message}</p>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Stage Review Modal */}
      {activeReviewStage && activeReviewOrder && (() => {
        const stage = selectedStageObj;
        const closeStage = () => {
          setActiveReviewStage(null);
          setActiveReviewOrder(null);
          setSelectedStageObj(null);
          setSelectedPerformerId('');
        };
        const isSupervisor = !currentUser.role || currentUser.role === 'Owner'
          || SUPERVISOR_ROLES.includes(currentUser.role);
        // One path for every forward move; the server decides whether the
        // role, the prerequisites and the stage's own data allow it.
        const transition = async (status, okMessage) => {
          if (stageTransitionBusy) return;
          setStageTransitionBusy(true);
          try {
            await api.transitionStage(
              activeReviewOrder.id,
              stage.stage_key,
              status,
              stageReviewComments,
              stageReviewImage ? [stageReviewImage] : [],
              selectedPerformerId || null
            );
            alert(okMessage);
            closeStage();
            fetchDashboardAndConfig();
          } catch (err) {
            alert("Failed to transition: " + err.message);
          } finally {
            setStageTransitionBusy(false);
          }
        };
        const tone = { COMPLETED: 'success', IN_PROGRESS: 'info', PAUSED: 'warning', SKIPPED: 'neutral' }[stage?.status] || 'neutral';
        const jobs = activeReviewOrder.garment_jobs || [];
        const answered = (obj) => Object.values(obj || {}).filter(v => v !== '' && v !== null && v !== undefined).length;
        const detailCount = jobs.reduce((n, j) => n + answered(j.spec) + answered(j.measurements), 0);
        const mins = Math.floor((stage?.duration_seconds || 0) / 60);
        const hrs = Math.floor(mins / 60);
        const duration = hrs > 0 ? `${hrs}h ${mins % 60}m` : `${mins}m`;
        const settled = stage && (stage.status === 'COMPLETED' || stage.status === 'SKIPPED');
        return (
          <FormModal
            icon={Scissors} tone="green" width="1000px" zIndex={1100}
            title={stage ? `Production Stage: ${stage.stage_name}` : `Stage Review: ${activeReviewStage}`}
            subtitle={`Order ID: ${orderRef(activeReviewOrder)}${activeReviewOrder.customer_name ? ` · ${activeReviewOrder.customer_name}` : ''}`}
            onClose={closeStage}
            footer={stage && (
              <>
                {(stage.status === 'NOT_STARTED' || stage.status === 'PAUSED') && (
                  <button className="btn-primary" disabled={stageTransitionBusy}
                          onClick={() => transition('IN_PROGRESS', 'Stage started successfully!')}>
                    <Play size={16} /> Start In-Progress
                  </button>
                )}
                {stage.status === 'IN_PROGRESS' && (
                  <>
                    <button className="btn-secondary at-btn-amber" disabled={stageTransitionBusy}
                            onClick={() => transition('PAUSED', 'Stage paused successfully!')}>
                      <Pause size={16} /> Pause Stage
                    </button>
                    <button className="btn-primary" disabled={stageTransitionBusy}
                            onClick={() => transition('COMPLETED', 'Stage completed successfully!')}>
                      <Check size={16} /> Complete Stage
                    </button>
                  </>
                )}
                {!settled && (
                  <button className="btn-secondary" disabled={stageTransitionBusy}
                          onClick={() => transition('SKIPPED', 'Stage skipped successfully!')}>
                    <SkipForward size={16} /> Skip Stage
                  </button>
                )}
                {/* Reversals. Forward-only is the rule; these are the two
                    audited exceptions, supervisors only, reason required.
                    The server enforces all of it -- these buttons only appear
                    where they could succeed. */}
                {settled && (currentUser?.role === 'Owner' || currentUser?.role === 'Master') && (
                  <button className="btn-secondary at-btn-warn" disabled={reversalBusy}
                          onClick={() => { setReversalReason(''); setReversalPrompt({ type: 'reopen' }); }}>
                    Reopen Stage…
                  </button>
                )}
                {stage.stage_key === 'master_quality_check' && stage.status !== 'COMPLETED'
                  && ['Owner', 'Master', 'QC Staff'].includes(currentUser?.role) && (
                  <button className="btn-secondary at-btn-danger" disabled={reversalBusy}
                          onClick={() => { setReversalReason(''); setReversalPrompt({ type: 'failqc' }); }}>
                    Fail QC — Send for Rework…
                  </button>
                )}
              </>
            )}
          >
            {/* What this stage is for, and where it stands. */}
            <div className="at-stage-summary">
              <div className="at-form-section" style={{ flexDirection: 'row', alignItems: 'center', gap: 'var(--space-4)' }}>
                <div className="kanban-thumb at-tile--green" style={{ width: 72, height: 90 }}>
                  {activeReviewOrder.completed_garment_image
                    ? <img src={activeReviewOrder.completed_garment_image} alt="" />
                    : <Shirt size={28} />}
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <span className="at-section-title" style={{ fontSize: 'var(--text-xl)' }}>{orderGarmentLabel(activeReviewOrder)}</span>
                    {detailCount > 0 && <span className="ui-badge ui-badge--neutral">{detailCount} details</span>}
                  </div>
                  <div className="at-section-sub" style={{ fontSize: 'var(--text-sm)', marginTop: '4px' }}>
                    {activeReviewOrder.customer_name}
                    {jobs.length > 1 ? ` · ${jobs.length} garments` : ''}
                    {activeReviewOrder.estimated_delivery ? ` · Delivery ${fmtDate(activeReviewOrder.estimated_delivery)}` : ''}
                  </div>
                  {activeReviewOrder.garment_label && jobs.length > 1 && (
                    <div className="at-section-sub">{activeReviewOrder.garment_label}</div>
                  )}
                </div>
              </div>
              {stage && (
                <div className="at-form-section at-stat--green" style={{ gap: 'var(--space-3)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                    <span className="ui-eyebrow" style={{ color: 'var(--text-primary)' }}>Status</span>
                    <span className={`ui-badge ui-badge--${tone}`}>● {stage.status.replace('_', ' ').toLowerCase()}</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
                    <div>
                      <div className="ui-eyebrow">Started</div>
                      <div className="stage-meta-value" style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <Calendar size={14} /> {stage.started_at ? fmtDateTime(stage.started_at) : '—'}
                      </div>
                    </div>
                    <div>
                      <div className="ui-eyebrow">SLA / target</div>
                      <div className="stage-meta-value" style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <Clock size={14} /> {stage.sla_hours} hours
                      </div>
                    </div>
                    {stage.completed_at && (
                      <div>
                        <div className="ui-eyebrow">Completed</div>
                        <div className="stage-meta-value">{fmtDateTime(stage.completed_at)}</div>
                      </div>
                    )}
                    {stage.duration_seconds > 0 && (
                      <div>
                        <div className="ui-eyebrow">Actual duration</div>
                        <div className="stage-meta-value">{duration}</div>
                      </div>
                    )}
                    {stage.performed_by_name && (
                      <div>
                        <div className="ui-eyebrow">Performed by</div>
                        <div className="stage-meta-value">{stage.performed_by_name}</div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* What is actually being made: the garments as the template
                groups them -- measurements, style, materials -- with the
                labels the order form used. Nested on the order payload, so it
                needs no fetch beyond the template itself. */}
            {jobs.length > 0 && (
              <OrderGarmentBrief
                jobs={jobs}
                specialInstructions={activeReviewOrder.special_instructions}
              />
            )}

            {/* The approved design, and the Master's note on how to make it.
                GET /design-studio/boards/ serves this and swaps in
                TailorBriefSerializer for a Tailor; the notes box lives here
                because the endpoint that writes it had nowhere else to be
                called from. */}
            {stageDesignBrief && stageDesignBrief.design && (
              <FormSection icon={Sparkles} tone="amber" title="Approved design"
                           subtitle="The design the owner approved, and how it is to be made.">
                <div style={{ display: 'flex', gap: '12px' }}>
                  {stageDesignBrief.design.image_url && (
                    <img src={resolveMediaUrl(stageDesignBrief.design.image_url)} alt="Approved design"
                         style={{ width: '84px', height: '110px', objectFit: 'cover', borderRadius: '6px', flexShrink: 0 }} />
                  )}
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600 }}>{stageDesignBrief.design.title}</div>
                    {stageDesignBrief.design.tailor_instructions && (
                      <div style={{ marginTop: '4px', color: 'var(--text-secondary)' }}>
                        {stageDesignBrief.design.tailor_instructions}
                      </div>
                    )}
                    {stageDesignBrief.design.customer_notes && (
                      <div style={{ marginTop: '4px', color: 'var(--text-secondary)' }}>
                        Customer: {stageDesignBrief.design.customer_notes}
                      </div>
                    )}
                  </div>
                </div>

                <label className="form-label" style={{ marginTop: '10px', display: 'block' }}>Production notes</label>
                <textarea className="form-control" rows={2}
                          placeholder="How this is to be made — cutting, finishing, anything the tailor needs."
                          value={productionNotesDraft}
                          onChange={(e) => setProductionNotesDraft(e.target.value)} />
                <button className="btn-secondary" style={{ marginTop: '6px', padding: '5px 10px', fontSize: '11px' }}
                        disabled={savingProductionNotes}
                        onClick={async () => {
                          setSavingProductionNotes(true);
                          try {
                            await api.saveProductionNotes(
                              stageDesignBrief.id, stageDesignBrief.design.id, productionNotesDraft);
                            const fresh = await api.getDesignBoards({ order_id: activeReviewOrder.order_id });
                            setStageDesignBrief(normaliseDesignBrief(Array.isArray(fresh) ? fresh[0] : fresh));
                          } catch (err) {
                            alert("Could not save the production notes: " + err.message);
                          } finally {
                            setSavingProductionNotes(false);
                          }
                        }}>
                  {savingProductionNotes ? 'Saving…' : 'Save notes'}
                </button>
              </FormSection>
            )}

            {stage && stage.comments && (
              <InfoNote icon={FileText} tone="neutral" title="Active notes / logs">
                &ldquo;{stage.comments}&rdquo;
              </InfoNote>
            )}

            {stage && stage.attachments && stage.attachments.length > 0 && (
              <div className="at-field">
                <span className="at-field-label">Progress photos ({stage.attachments.length})</span>
                <div className="at-photos">
                  {stage.attachments.map((url, i) => (
                    <a key={i} href={url} target="_blank" rel="noreferrer" style={{ lineHeight: 0 }}>
                      <PhotoTile src={url} alt={`attachment-${i}`} size={72} />
                    </a>
                  ))}
                </div>
              </div>
            )}

            {/* Hand this stage to someone, say who did the work, note what
                happened, photograph it. assign_stage and the performer field
                are supervisor calls; the API refuses them from anyone else. */}
            <FormSection icon={RefreshCw} tone="green" title="Manage Stage Transition">
              <div className="at-form-grid">
                {stage && isSupervisor && (
                  <Field label="Assign this stage to" icon={User}>
                    <select
                      className="form-control"
                      value={stage.assigned_to || ''}
                      disabled={assigningStageKey === stage.stage_key}
                      onChange={(e) => handleAssignStage(activeReviewOrder.id, stage.stage_key, e.target.value)}
                    >
                      <option value="">Unassigned</option>
                      {eligibleStaffForStage(stage.stage_key).map(t => (
                        <option key={t.id} value={t.id}>{t.name} · {t.role}</option>
                      ))}
                    </select>
                  </Field>
                )}
                {isSupervisor && (
                  <Field label="Record who performed this" icon={Users}>
                    <select
                      className="form-control"
                      value={selectedPerformerId}
                      onChange={(e) => setSelectedPerformerId(e.target.value)}
                    >
                      <option value="">-- Select Tailor / Master --</option>
                      {(stage ? eligibleStaffForStage(stage.stage_key) : tailors).map(t => (
                        <option key={t.id} value={t.id}>{t.name} ({t.role})</option>
                      ))}
                    </select>
                  </Field>
                )}
                <Field label="Comments / Fitting Logs">
                  <textarea
                    className="form-control"
                    placeholder="Enter notes, alterations details, or comments..."
                    value={stageReviewComments}
                    onChange={(e) => setStageReviewComments(e.target.value)}
                  />
                </Field>
                <div className="at-field">
                  <span className="at-field-label">Upload Progress Photo</span>
                  {stageReviewImage ? (
                    <div className="at-photos">
                      <PhotoTile src={URL.createObjectURL(stageReviewImage)} size={88}
                                 onRemove={() => setStageReviewImage(null)} />
                    </div>
                  ) : (
                    <Dropzone compact camera
                              title="Drag & drop an image here" subtitle="or choose a file"
                              chooseLabel="Choose file" cameraLabel="Take photo"
                              onFiles={(files) => setStageReviewImage(files[0])} />
                  )}
                </div>
              </div>
            </FormSection>
          </FormModal>
        );
      })()}

      {/* AI Draping Modal */}
      {showDrapingModal && selectedFabric && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundColor: 'rgba(0,0,0,0.75)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1200,
          backdropFilter: 'blur(4px)'
        }}>
          <div style={{
            backgroundColor: '#0d0d0d',
            borderRadius: '16px',
            border: '1px solid rgba(212, 175, 55, 0.25)',
            width: '800px',
            maxWidth: '95%',
            padding: '24px',
            boxShadow: '0 12px 40px rgba(0,0,0,0.5)',
            display: 'flex',
            flexDirection: 'column',
            gap: '20px',
            color: '#fff'
          }}>
            <style>{`
              @keyframes modalSpin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
              }
            `}</style>
            
            {/* Modal Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                <Sparkles size={20} style={{ color: 'var(--accent-text, #b07c40)', flexShrink: 0 }} />
                <h3 style={{ fontSize: 'clamp(14px, 4.2vw, 18px)', fontWeight: 700, margin: 0, letterSpacing: '0.5px' }}>Scaleezy Live Visualizer: Interactive Fabric Draping</h3>
              </div>
              <button 
                type="button"
                aria-label="Close visualizer"
                onClick={() => { setShowDrapingModal(false); }}
                style={{ background: 'none', border: 'none', color: '#888', fontSize: '20px', cursor: 'pointer', outline: 'none', flexShrink: 0, minWidth: '44px', minHeight: '44px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
              >
                &times;
              </button>
            </div>

            {/* Modal Content Grid */}
            {/* `repeat(auto-fit, minmax(min(190px, 100%), 1fr))`, not a fixed
                `1.2fr 1.2fr 1.6fr`: three fixed columns put the third panel --
                the one carrying the Try On explanation -- 70px past the right
                edge of a 320px screen, where it was clipped and unreadable.
                auto-fit keeps all three side by side wherever they fit and
                stacks them when they do not. */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(190px, 100%), 1fr))', gap: '20px', alignItems: 'stretch' }}>
              {/* Left Column: Style Sketch */}
              <div style={{ background: '#141414', border: '1px solid rgba(255, 255, 255, 0.05)', borderRadius: '8px', padding: '16px', textAlign: 'center', display: 'flex', flexDirection: 'column', gap: '10px', justifyContent: 'center' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>Selected Style Sketch</span>
                {selectedDesignTemplates.length > 0 ? (
                  <div style={{ width: '100%', height: '180px', overflow: 'hidden', borderRadius: '6px' }}>
                    <img src={selectedDesignTemplates[0]} alt="Design Sketch" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  </div>
                ) : (
                  <div style={{ width: '100%', height: '180px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px dashed rgba(255,255,255,0.1)' }}>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>No sketch selected</span>
                  </div>
                )}
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#fff' }}>{customerForm.garment_type || "Bespoke Cut"}</span>
              </div>

              {/* Middle Column: Fabric Swatch */}
              <div style={{ background: '#141414', border: '1px solid rgba(255, 255, 255, 0.05)', borderRadius: '8px', padding: '16px', textAlign: 'center', display: 'flex', flexDirection: 'column', gap: '10px', justifyContent: 'center' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>Selected Fabric Swatch</span>
                <div style={{ width: '100%', height: '180px', overflow: 'hidden', borderRadius: '6px' }}>
                  <img 
                    src={resolveMediaUrl(selectedFabric.image_url, 'https://images.unsplash.com/photo-1574169208507-84376144848b?w=400')} 
                    alt="Fabric Swatch" 
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
                  />
                </div>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#fff' }}>{selectedFabric.name} ({selectedFabric.color})</span>
              </div>

              {/* Right Column: Draped Mannequin View */}
              <div style={{ background: '#181818', border: '1px solid rgba(212, 175, 55, 0.15)', borderRadius: '8px', padding: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', position: 'relative', minHeight: '260px' }}>
                {!drapingCompleted && !drapingLoading ? (
                  <div style={{ textAlign: 'center', padding: '20px' }}>
                    <div style={{ color: 'var(--accent-text, #b07c40)', marginBottom: '12px' }}><Sparkles size={36} /></div>
                    <h4 style={{ fontSize: '14px', fontWeight: 600, color: '#fff', marginBottom: '8px' }}>Ready to Drape</h4>
                    <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '16px', maxWidth: '220px', margin: '0 auto 16px' }}>
                      Click "Start Try On" to simulate draping this fabric onto the mannequin.
                    </p>
                  </div>
                ) : drapingLoading ? (
                  <div style={{ textAlign: 'center', padding: '20px' }}>
                    <div className="spinner" style={{ border: '3px solid rgba(255,255,255,0.1)', borderTop: '3px solid var(--accent-text, #b07c40)', borderRadius: '50%', width: '40px', height: '40px', animation: 'modalSpin 1s linear infinite', margin: '0 auto 16px' }} />
                    <h4 style={{ fontSize: '14px', fontWeight: 600, color: '#fff', marginBottom: '4px' }}>Simulating Try On...</h4>
                    <p style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic' }}>Mapping coordinates onto sketch layers</p>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px', width: '100%' }}>
                    <span style={{ fontSize: '11px', color: 'var(--accent-text, #b07c40)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1px' }}>✨ 3D Mannequin Draped View</span>
                    <div style={{ width: '100%', height: '200px', overflow: 'hidden', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.08)' }}>
                      <img src={drapedImage} alt="Draped Mannequin Mockup" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Modal Disclaimer */}
            <div style={{ fontSize: '11px', color: 'rgba(255, 255, 255, 0.4)', fontStyle: 'italic', textAlign: 'left', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '10px' }}>
              ⚠️ Reference Simulation Only — actual handcrafting details may vary depending on tailoring cuts and fabric stretch.
            </div>

            {/* Modal Actions Footer */}
            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'flex-end', gap: '12px', marginTop: '8px' }}>
              <button 
                type="button" 
                className="btn-secondary" 
                style={{ padding: '8px 16px', fontSize: '12px' }}
                onClick={() => { setShowDrapingModal(false); }}
              >
                Cancel
              </button>
              
              {!drapingCompleted && !drapingLoading && (
                <button 
                  type="button" 
                  className="btn-primary" 
                  style={{ padding: '8px 16px', fontSize: '12px', background: 'linear-gradient(135deg, #d35400, #e67e22)', border: 'none' }}
                  onClick={() => {
                    setDrapingLoading(true);
                    setTimeout(() => {
                      setDrapedImage(getDrapedPreviewImage(selectedFabric, selectedDesignTemplates[0] || ''));
                      setDrapingLoading(false);
                      setDrapingCompleted(true);
                    }, 2000);
                  }}
                >
                  Start Try On
                </button>
              )}

              {drapingCompleted && (
                <>
                  <button 
                    type="button" 
                    className="btn-secondary" 
                    style={{ padding: '8px 16px', fontSize: '12px', border: '1px dashed rgba(255, 255, 255, 0.2)' }}
                    onClick={() => {
                      setDrapingCompleted(false);
                    }}
                  >
                    Re-try / Change
                  </button>
                  <button 
                    type="button" 
                    className="btn-primary" 
                    style={{ padding: '8px 16px', fontSize: '12px', backgroundColor: '#107c41' }}
                    onClick={() => {
                      setShowDrapingModal(false);
                    }}
                  >
                    Confirm & Save
                  </button>
                </>
              )}
            </div>

          </div>
        </div>
      )}

      <NetworkActivityBar />
      {reversalPrompt && (
        <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1300 }}>
          <div className="search-modal-card" style={{ maxWidth: '420px', width: '100%', padding: '24px' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)', marginBottom: '8px' }}>
              {reversalPrompt.type === 'failqc' ? 'Fail this quality check?' : 'Reopen this stage?'}
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
              {reversalPrompt.type === 'failqc'
                ? 'The stitching stages reopen for rework and the order drops back to Design & Creation. Say what was wrong — the tailor doing the rework reads this.'
                : 'This goes on the order\u2019s record with your name. Say why the stage is being reopened.'}
            </p>
            <textarea
              className="form-control"
              rows={3}
              autoFocus
              placeholder={reversalPrompt.type === 'failqc' ? 'e.g. Hem is crooked on the left panel' : 'e.g. Completed on the wrong order'}
              value={reversalReason}
              onChange={(e) => setReversalReason(e.target.value)}
              style={{ marginBottom: '16px' }}
            />
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button type="button" className="btn-secondary" disabled={reversalBusy} onClick={() => setReversalPrompt(null)}>
                Cancel
              </button>
              <button
                type="button" className="btn-primary" disabled={reversalBusy || !reversalReason.trim()}
                onClick={async () => {
                  if (reversalBusy) return;
                  setReversalBusy(true);
                  try {
                    if (reversalPrompt.type === 'failqc') {
                      await api.failQualityCheck(activeReviewOrder.id, reversalReason.trim());
                    } else {
                      await api.reopenStage(activeReviewOrder.id, selectedStageObj.stage_key, reversalReason.trim());
                    }
                    setReversalPrompt(null);
                    setActiveReviewStage(null);
                    setActiveReviewOrder(null);
                    setSelectedStageObj(null);
                    fetchDashboardAndConfig();
                  } catch (err) {
                    alert(err.message);
                  } finally {
                    setReversalBusy(false);
                  }
                }}
              >
                {reversalBusy ? 'Recording…' : (reversalPrompt.type === 'failqc' ? 'Fail QC' : 'Reopen Stage')}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Rendered at the root so both sidebars' Logout items reach it,
          whichever view is on screen. */}
      {showLogoutConfirm && (
        <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1300 }}>
          <div className="search-modal-card" style={{ maxWidth: '360px', width: '100%', padding: '24px', textAlign: 'center' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)', marginBottom: '8px' }}>
              Log out?
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px' }}>
              You will need to sign in again to open your boutique.
            </p>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
              <button type="button" className="btn-secondary" disabled={logoutBusy} onClick={() => setShowLogoutConfirm(false)}>
                Cancel
              </button>
              <button type="button" className="btn-primary" disabled={logoutBusy} onClick={handleLogout}>
                {logoutBusy ? 'Logging out…' : 'Logout'}
              </button>
            </div>
          </div>
        </div>
      )}

      <GarmentPairingModal
        isOpen={!!activePairingGarment}
        onClose={() => setActivePairingGarment(null)}
        primaryGarmentKey={activePairingGarment?.key}
        primaryGarmentName={activePairingGarment?.name}
        garmentTemplates={garmentTemplates}
        garmentJobs={garmentJobs}
        onAddPairedGarments={handleAddPairedGarments}
        onSaveReferenceImage={handleSaveReferenceImage}
      />
    </div>
  );
}

export default App;
