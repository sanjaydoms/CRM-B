import React, { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { 
  Users, ShoppingBag, Scissors, Search, 
  Upload, Check, ArrowRight, ArrowLeft, Heart, 
  MessageSquare, Star, Copy, ShieldCheck, Compass, BarChart2,
  FolderOpen, Sparkles, HelpCircle, X, ExternalLink,
  ChevronRight, Lock, Mail, Phone, Calendar, Landmark, 
  FileText, Bell, User, MapPin, Eye, EyeOff, Edit2, Plus, Trash2, LogOut, History, Package, Menu,
  PenTool, Settings
} from 'lucide-react';
import { api } from './services/api';
import { resolveMediaUrl } from './services/media';
import {
  formatMoney, formatDate as fmtDate, formatDateTime as fmtDateTime,
  formatTime as fmtTime, setBoutiqueTimeZone,
} from './services/format';
// The inventory panel and the design studio are whole screens behind their own
// tabs, and together they are a sixth of the bundle. Loading them eagerly made
// every first paint -- including the login screen -- wait on code most sessions
// never open, so they are fetched when their tab is first shown instead.
// TemplateForm stays eager: it renders inline in the order wizard, where a
// loading flicker mid-form would be worse than its few KB.
const DesignStudio = lazy(() => import('./features/designStudio/DesignStudio'));
const InventoryPanel = lazy(() => import('./features/inventory/InventoryPanel'));
const DesignLibrary = lazy(() => import('./features/designStudio/DesignLibrary'));
const DesignDashboard = lazy(() => import('./features/designStudio/DesignDashboard'));
const DesignWork = lazy(() => import('./features/designStudio/DesignWork'));
import TemplateForm from './features/catalog/TemplateForm';
import GarmentSummary from './features/catalog/GarmentSummary';
import { MobileHeader } from './components/ui/MobileHeader';
import { useLanguage } from './i18n/LanguageContext.jsx';
import LanguageSelector from './components/LanguageSelector.jsx';
import SettingsPage from './components/SettingsPage.jsx';
import { BottomNavigation } from './components/ui/BottomNavigation';

import { BottomSheet } from './components/ui/BottomSheet';
import { ResponsiveCard } from './components/ui/ResponsiveCard';
import { ProgressiveAccordion } from './components/ui/ProgressiveAccordion';

/** Placeholder shown while a lazily loaded screen arrives. */
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
// seven role strings beyond 'Tailor' and 'Master' -- and get_default_workflow
// permits each of them on a specific stage. Comparing against the two literal
// names stranded every specialist: routed to a tab their own nav does not
// contain, and shown an order's money that the permission matrix says
// production staff must not see.
const PRODUCTION_ROLES = [
  'Tailor', 'Master', 'Measurement Master', 'Pattern Master', 'Cutting Master',
  'Maggam Master', 'Finishing Master', 'Pressing Staff', 'QC Master',
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
  { value: 'Measurement Master', label: 'Measurement Master', hint: 'Takes and verifies client measurements.' },
  { value: 'Pattern Master', label: 'Pattern Master', hint: 'Drafts the paper pattern.' },
  { value: 'Cutting Master', label: 'Cutting Master', hint: 'Cuts fabric from the pattern.' },
  { value: 'Maggam Master', label: 'Maggam Master', hint: 'Runs embroidery before stitching.' },
  { value: 'Finishing Master', label: 'Finishing Master', hint: 'Hemming and final shaping.' },
  { value: 'Pressing Staff', label: 'Pressing Staff', hint: 'Presses the garment before dispatch.' },
  { value: 'QC Master', label: 'QC Master', hint: 'Runs the quality inspection.' },
];

// Where a design came from. Mirrors DesignPreference.SOURCE_CHOICES.
const DESIGN_SOURCES = [
  { value: 'BOUTIQUE_CATALOG', label: 'Boutique catalogue' },
  { value: 'CUSTOM_DESIGN', label: 'Custom design' },
  { value: 'PREVIOUS_DESIGN', label: 'Previous design' },
  { value: 'PINTEREST', label: 'Pinterest' },
  { value: 'GOOGLE', label: 'Google images' },
  { value: 'CUSTOMER_SKETCH', label: 'Customer sketch' },
  { value: 'DESIGNER_SKETCH', label: 'Designer sketch' },
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

// A stored spec value as a person reads it. Stored values are the template's own
// option keys -- 'a_line', 'hr2', 'hand_made' -- and booleans, both of which
// reached the shop floor raw.
const humaniseSpecValue = (value) => {
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  if (Array.isArray(value)) return value.map(humaniseSpecValue).join(', ');
  return humaniseSpecKey(value);
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
        <button
          type="button"
          className="btn-secondary"
          style={{ fontSize: '12px', padding: '6px 10px' }}
          disabled={busy}
          onClick={() => fileRef.current?.click()}
        >
          {busy ? 'Working…' : t('ordersPage.addPhoto', 'Add photo')}
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
  const [dashboardTab, setDashboardTab] = useState('overview'); // 'overview', 'fabrics', 'tailors', 'designs'
  const [currentUser, setCurrentUser] = useState(null);
  const { t, language } = useLanguage();
  const currentUserName = currentUser?.first_name || currentUser?.name || currentUser?.email?.split('@')[0] || 'User';

  
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
  const [fabricTab, setFabricTab] = useState('boutique'); // 'my-fabric', 'boutique'
  const [paymentPhase, setPaymentPhase] = useState(false);
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
  const [fabricFilter, setFabricFilter] = useState('All');
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
  const [fabricForm, setFabricForm] = useState({
    name: '',
    material: '',
    color: '',
    price_per_meter: '',
    image_url: '',
    is_available: true
  });

  // Tailors CRUD State
  const [showTailorModal, setShowTailorModal] = useState(false);
  const [editingTailor, setEditingTailor] = useState(null);
  const [shareCredsTailor, setShareCredsTailor] = useState(null);
  // Recording a payment: which row is in flight, and what went wrong. Shown in
  // the Invoices header rather than through alert() -- a modal dialog over a
  // ledger the owner is reading down is the wrong shape for "that did not save".
  const [wizardError, setWizardError] = useState(null);
  const [savingPaymentId, setSavingPaymentId] = useState(null);
  const [paymentError, setPaymentError] = useState(null);
  const [tailorForm, setTailorForm] = useState({
    name: '',
    email: '',
    specialty: '',
    rating: 5.0,
    status: 'Available',
    role: 'Tailor'
  });

  // Designs CRUD State
  const [showDesignModal, setShowDesignModal] = useState(false);
  const [editingDesign, setEditingDesign] = useState(null);
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

  const addGarment = async (key) => {
    if (garmentJobs.some(job => job.key === key)) return;
    try {
      const template = await api.getGarmentTemplate(key);
      setGarmentJobs(prev => [...prev, {
        key, template, values: {}, quantities: {},
        pricing: { base: GARMENT_PRICES[template.name] || 15000, fabric: 0,
                   embroidery: 0, customization: 0, tailoring: 0 },
      }]);
    } catch (err) {
      console.error(err);
      alert('Could not load that garment form.');
    }
  };

  useEffect(() => {
    if (view === 'wizard' && garmentJobs.length === 0 && garmentTemplates.length > 0) {
      addGarment(garmentTemplates[0].key);
    }
  }, [view, garmentJobs.length, garmentTemplates]);

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

  /** The material fields on a template, with the item chosen for each.
   *
   *  Read off the template rather than off a hardcoded list, so a garment that
   *  gains a material field gains a material line with it. */
  const garmentMaterialFields = (job) => (
    (job.template?.sections || [])
      .flatMap(section => section.fields || [])
      .filter(field => field.field_type === 'inventory_ref')
      .map(field => ({ field, itemId: job.values?.[field.key] }))
      .filter(entry => entry.itemId)
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
      materials: garmentMaterialFields(job).map(({ field, itemId }) => ({
        field_key: field.key,
        inventory_item: itemId,
        quantity: job.quantities?.[field.key],
        source: 'STORE',
      })),
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
          pricing: garment.pricing || {},
          design: garment.design || {},
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

  /** Persist one GarmentJob per dress once the order exists to hang them on.
   *
   *  Materials go with the job rather than after it. A material selection used
   *  to survive only as a bare item id inside `spec`, which no part of the
   *  inventory system reads -- so an order could name six materials, reach
   *  Delivered, and leave stock untouched. As JobMaterial rows with a quantity
   *  they become a material plan, and the plan is what reserves and consumes.
   */
  const saveGarmentJobs = async (orderId) => {
    for (const job of garmentJobs) {
      const { spec, measurements } = splitSpec(job.template, job.values);
      const materials = garmentMaterialFields(job).map(({ field, itemId }) => ({
        field_key: field.key,
        inventory_item: itemId,
        quantity: job.quantities?.[field.key],
        // Always STORE: these lines exist only because an inventory item was
        // picked off the boutique's own racks. A garment marked "customer
        // provided fabric" is the common case where the client brings the cloth
        // and the boutique still supplies the lining, hooks and thread -- those
        // trims are boutique stock and must be deducted. The customer's own
        // material is not a line here at all; it lives in CustomerMaterial,
        // which is a separate ledger and never touches boutique stock.
        source: 'STORE',
      }));
      try {
        await api.createGarmentJob({
          order: orderId,
          template: job.template.id,
          spec,
          measurements,
          materials,
        });
      } catch (err) {
        console.error(`Could not save the ${job.template.name} on this order`, err);
        throw err;
      }
    }
  };

  // Active Selected Dashboard Order for progress tracker
  const [selectedDashboardOrder, setSelectedDashboardOrder] = useState(null);
  const [expandedDna, setExpandedDna] = useState({});
  const [selectedDirectoryCustomer, setSelectedDirectoryCustomer] = useState(null);
  const [directoryDetailLoading, setDirectoryDetailLoading] = useState(false);
  // Which order in the customer profile is expanded to show its production
  // progress. Opening a client's order used to throw them into the new-order
  // wizard, so there was no way to answer "where is my dress?" from the profile.
  const [expandedCustomerOrderId, setExpandedCustomerOrderId] = useState(null);
  const [approvingDesignId, setApprovingDesignId] = useState(null);
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
  const [invoiceSearch, setInvoiceSearch] = useState('');
  const [invoiceFilter, setInvoiceFilter] = useState('All');
  const [loading, setLoading] = useState(true);
  const [boutiqueSettings, setBoutiqueSettings] = useState(null);
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

    const load = (label, request, apply) =>
      request().then(apply, (err) => {
        console.error(`Failed to load ${label}`, err);
        setLoadErrors((prev) => (prev.includes(label) ? prev : [...prev, label]));
      });

    const requests = [
      load('dashboard', api.getDashboard, (data) => {
        setDashboardData(data);
        if (data.recent_orders?.length > 0) {
          // Keep the user's chosen order selected, but re-read it from the fresh
          // payload -- holding on to the old object left the stage tracker showing
          // pre-change data after every refresh.
          setSelectedDashboardOrder((current) => {
            if (!current) return data.recent_orders[0];
            return data.recent_orders.find(o => o.id === current.id) || current;
          });
        }
      }),
      load('customers', api.getCustomers, (data) => {
        setCustomersList(data);
        setAllCustomers(data);
      }),
      load('orders', api.getOrders, setOrdersList),
      load('tailors', api.getTailors, setTailors),
      load('appointments', api.getAppointments, setAppointments),
      load('fabrics', api.getFabrics, setFabrics),
      load('designs', api.getAllBoutiqueDesigns, setAllDesigns),
      load('settings', api.getBoutiqueSettings, (data) => {
        setBoutiqueSettings(data);
        // Every date and time this session renders now uses the boutique's own
        // clock, matching what the server prints on the customer's page.
        setBoutiqueTimeZone(data?.timezone);
      }),
      load('notifications', () => fetchNotifications(user), () => {})
    ];

    // Owner-only endpoint: each queued message carries the order's tracking
    // link, which reaches the order's totals without signing in. Asking for it
    // as anyone else is a guaranteed 403 and would show them a load error for
    // something they are not missing.
    if (!user?.role || user.role === 'Owner') {
      requests.push(load('customer messages', api.getQueuedCustomerMessages, setQueuedMessages));
    }

    await Promise.all(requests);
    setLoading(false);
  };

  /** Record that the owner sent a queued message from their own WhatsApp. */
  const handleMarkMessageSent = async (orderId, messageId) => {
    await api.markMessageSent(orderId, messageId);
    // The queue holds only what is still waiting, so a sent one leaves it.
    setQueuedMessages((prev) => prev.filter((m) => m.id !== messageId));
  };

  // Catalog Management Handlers
  const handleSaveFabric = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...fabricForm,
        price_per_meter: parseFloat(fabricForm.price_per_meter) || 0.00
      };
      if (editingFabric) {
        await api.updateFabric(editingFabric.id, payload);
      } else {
        if (!payload.image_url) {
          // Curated Unsplash fabric texture image
          payload.image_url = 'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400';
        }
        await api.createFabric(payload);
      }
      setShowFabricModal(false);
      setEditingFabric(null);
      setFabricForm({ name: '', material: '', color: '', price_per_meter: '', image_url: '', is_available: true });
      fetchDashboardAndConfig();
    } catch (err) {
      alert("Failed to save fabric: " + err.message);
    }
  };

  const handleDeleteFabric = async (id) => {
    if (window.confirm("Are you sure you want to delete this fabric?")) {
      try {
        await api.deleteFabric(id);
        fetchDashboardAndConfig();
      } catch (err) {
        alert("Failed to delete fabric: " + err.message);
      }
    }
  };

  const handleSaveAppointment = async (e) => {
    e.preventDefault();
    if (savingAppointment) return;
    setSavingAppointment(true);
    try {
      await api.createAppointment({
        ...appointmentForm,
        assigned_staff: appointmentForm.assigned_staff || null,
        scheduled_time: new Date(appointmentForm.scheduled_time).toISOString(),
      });
      const fresh = await api.getAppointments();
      setAppointments(fresh);
      setShowAppointmentModal(false);
      setAppointmentForm({
        customer: '', appointment_type: 'TRIAL', scheduled_time: '', assigned_staff: '', notes: '',
      });
    } catch (err) {
      alert("Could not book the appointment: " + err.message);
    } finally {
      setSavingAppointment(false);
    }
  };

  const handleSaveTailor = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...tailorForm,
        rating: parseFloat(tailorForm.rating) || 5.0
      };
      const saved = editingTailor
        ? await api.updateTailor(editingTailor.id, payload)
        : await api.createTailor(payload);
      setShowTailorModal(false);
      setEditingTailor(null);
      setTailorForm({ name: '', email: '', specialty: '', rating: 5.0, status: 'Available', role: 'Tailor' });
      fetchDashboardAndConfig();
      // The server generates this account's password and returns it on this one
      // response, never again -- so if it is here, show it now. Opening the
      // share panel straight away is the point: closing this without reading it
      // means the only way to give them a password is a reset link.
      if (saved && saved.bootstrap_password) {
        setShareCredsTailor(saved);
      }
    } catch (err) {
      alert("Failed to save tailor: " + err.message);
    }
  };

  const handleDeleteTailor = async (id) => {
    if (window.confirm("Are you sure you want to delete this tailor?")) {
      try {
        await api.deleteTailor(id);
        fetchDashboardAndConfig();
      } catch (err) {
        alert("Failed to delete tailor: " + err.message);
      }
    }
  };

  const handleAssignWorkflow = async (orderId, updates) => {
    try {
      await api.updateOrder(orderId, updates);
      fetchDashboardAndConfig();
    } catch (err) {
      alert("Failed to update staff assignment: " + err.message);
    }
  };

  const handleSaveDesign = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...designForm,
        price: parseFloat(designForm.price) || 0.00,
        is_boutique: designForm.is_boutique === true || designForm.is_boutique === 'true'
      };
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
    if (!loginEmail || !loginPassword) {
      alert("Please fill in all credentials.");
      return;
    }
    setAuthError(null);
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
    await api.logout();
    setCurrentUser(null);
    setView('login');
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
        if (fabricTab === 'boutique' && !selectedFabric) {
          alert("Please select a fabric from the catalog or upload your own fabric.");
          return;
        }
        await saveStep2();
        setCurrentStep(3);
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

  const handleDesignFilesChange = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
      setDesignFiles(prev => [...prev, ...files]);
      files.forEach(file => {
        const reader = new FileReader();
        reader.onloadend = () => {
          setDesignPreviews(prev => [...prev, reader.result]);
        };
        reader.readAsDataURL(file);
      });
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
  const handleGarmentBoardChange = (garmentKey, state) => {
    if (state?.items !== undefined) {
      setGarmentJobs(prev => prev.map(job => job.key === garmentKey
        ? { ...job, design: { items: state.items, selected: state.selected || null } }
        : job));
    }
    setDesignBoard(state);
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
    // QC Master is never order.tailor (the stitcher) or order.master (the
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
  // These pickers filtered `t.role !== 'Master'`, which passes all SEVEN
  // specialist roles -- Measurement, Pattern, Cutting, Maggam, Finishing,
  // Pressing and QC Master -- while get_default_workflow restricts both
  // stitching stages to ["Owner", "Tailor"]. So the owner could hand the
  // stitching to the Finishing Master, the order was accepted, and that person
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

              <button type="submit" className="btn-primary" style={{ justifyContent: 'center', padding: '14px', borderRadius: '8px', fontWeight: 600, fontSize: '14px' }}>
                Login to Workspace
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
        <div className="portal-layout">
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
              api.markNotificationsAsRead(currentUser.role || 'Owner', currentUser.email)
                .then(() => fetchNotifications())
                    // Never let the bell take the app down: a refused or failed
                    // mark-read is not worth losing the session over.
                    .catch(() => {});
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
                onClick={() => {
                  setShowNotificationsDrawer(true);
                  api.markNotificationsAsRead(currentUser.role || 'Owner', currentUser.email)
                    .then(() => fetchNotifications())
                    // Never let the bell take the app down: a refused or failed
                    // mark-read is not worth losing the session over.
                    .catch(() => {});
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
              <div className="portal-sidebar-logo">SCALEEZY</div>
              <div className="portal-sidebar-logo-sub">THE ATELIER EXPERIENCE</div>
            </div>

            <div className="desktop-inbox-alert-btn" style={{ padding: '0 20px', marginBottom: '16px', marginTop: '16px' }}>
              <button 
                onClick={() => {
                  setShowNotificationsDrawer(true);
                  api.markNotificationsAsRead(currentUser.role || 'Owner', currentUser.email)
                    .then(() => fetchNotifications())
                    // Never let the bell take the app down: a refused or failed
                    // mark-read is not worth losing the session over.
                    .catch(() => {});
                }}
                className="btn-secondary"
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  position: 'relative',
                  padding: '10px 16px',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  fontSize: '13px',
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  backgroundColor: 'rgba(0,0,0,0.02)'
                }}
              >
                <Bell size={16} />
                <span>{t('common.inboxAlerts', 'Inbox Alerts')}</span>
                {notifications.filter(n => !n.is_read).length > 0 && (
                  <span style={{
                    backgroundColor: '#ff4d4d',
                    color: '#fff',
                    borderRadius: '10px',
                    padding: '2px 8px',
                    fontSize: '10px',
                    fontWeight: 700
                  }}>
                    {notifications.filter(n => !n.is_read).length}
                  </span>
                )}
              </button>
            </div>

            <nav className="portal-menu">
              {(!currentUser.role || currentUser.role === 'Owner') ? (
                <>
                  <a className={`portal-menu-item ${dashboardTab === 'overview' ? 'active' : ''}`} onClick={() => { setDashboardTab('overview'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Users size={16} /> {t('nav.dashboard')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'orders' ? 'active' : ''}`} onClick={() => { setDashboardTab('orders'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><ShoppingBag size={16} /> {t('nav.manageOrders')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'customers' ? 'active' : ''}`} onClick={() => { setDashboardTab('customers'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Users size={16} /> {t('nav.customers')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'invoices' ? 'active' : ''}`} onClick={() => { setDashboardTab('invoices'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><FileText size={16} /> {t('nav.invoices')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'analytics' ? 'active' : ''}`} onClick={() => { setDashboardTab('analytics'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><BarChart2 size={16} /> {t('nav.analytics')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'fabrics' ? 'active' : ''}`} onClick={() => { setDashboardTab('fabrics'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Compass size={16} /> {t('nav.manageFabrics')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'inventory' ? 'active' : ''}`} onClick={() => { setDashboardTab('inventory'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Package size={16} /> {t('nav.inventory')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'tailors' ? 'active' : ''}`} onClick={() => { setDashboardTab('tailors'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Scissors size={16} /> {t('nav.manageTailors')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'designs' ? 'active' : ''}`} onClick={() => { setDashboardTab('designs'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Sparkles size={16} /> {t('nav.manageDesigns')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'designWork' ? 'active' : ''}`} onClick={() => { setDashboardTab('designWork'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><PenTool size={16} /> {t('nav.designWork')}</a>
                </>
              ) : currentUser.role === 'Master' ? (
                <>
                  <a className={`portal-menu-item ${dashboardTab === 'assignments' ? 'active' : ''}`} onClick={() => { setDashboardTab('assignments'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Scissors size={16} /> {t('nav.myAssignments')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'orders' ? 'active' : ''}`} onClick={() => { setDashboardTab('orders'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><ShoppingBag size={16} /> {t('nav.manageOrders')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'customers' ? 'active' : ''}`} onClick={() => { setDashboardTab('customers'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Users size={16} /> {t('nav.customers')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'designWork' ? 'active' : ''}`} onClick={() => { setDashboardTab('designWork'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><PenTool size={16} /> {t('nav.designWork')}</a>
                </>
              ) : currentUser.role === 'Designer' ? (
                <>
                  <a className={`portal-menu-item ${dashboardTab === 'designWork' ? 'active' : ''}`} onClick={() => { setDashboardTab('designWork'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><PenTool size={16} /> {t('nav.myWork')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'designs' ? 'active' : ''}`} onClick={() => { setDashboardTab('designs'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Sparkles size={16} /> {t('nav.designStudio')}</a>
                </>
              ) : (
                <a className={`portal-menu-item ${dashboardTab === 'assignments' ? 'active' : ''}`} onClick={() => { setDashboardTab('assignments'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Scissors size={16} /> {t('nav.myAssignments')}</a>
              )}
              <a className={`portal-menu-item ${dashboardTab === 'account' ? 'active' : ''}`} onClick={() => { setDashboardTab('account'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><User size={16} /> {t('nav.account')}</a>
              <a className={`portal-menu-item ${dashboardTab === 'settings' ? 'active' : ''}`} onClick={() => { setDashboardTab('settings'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Settings size={16} /> {t('nav.settings')}</a>
              <a className="portal-menu-item" onClick={() => { handleLogout(); setMobileNavOpen(false); }}><LogOut size={16} /> {t('nav.logout')}</a>
            </nav>


            <div className="portal-sidebar-footer">
              {/* Opened wa.me/919876543210 -- an invented number belonging to
                  a real stranger, offered to boutique staff as their "style
                  concierge". Rendered only when the boutique has given its own
                  number, and pointed at that. */}
              {boutiqueSettings?.phone && (
                <div className="portal-sidebar-help">
                  <h4 style={{ fontSize: '12px', fontWeight: 700 }}>Need Help?</h4>
                  <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Message your boutique directly.</p>
                  <button
                    className="whatsapp-btn"
                    style={{ width: '100%', padding: '6px', fontSize: '11px' }}
                    onClick={() => window.open(`https://wa.me/${String(boutiqueSettings.phone).replace(/\D/g, '')}`)}
                  >
                    <MessageSquare size={12} />
                    Chat Now
                  </button>
                </div>
              )}
            </div>
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
                                <span style={{ fontWeight: 700, fontSize: '16px', color: 'var(--text-primary)' }}>Order ID: {order.order_id}</span>
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
                                  onChange={(e) => {
                                    api.updateOrderStatus(order.id, e.target.value)
                                      .then(() => fetchDashboardAndConfig())
                                      .catch(err => alert("Failed to update status: " + err.message));
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
                                          onChange={async (e) => {
                                            const updatedVerification = {
                                              ...(order.master_verification || {}),
                                              [item.key]: e.target.checked
                                            };
                                            try {
                                              await api.saveMasterVerification(order.id, updatedVerification);
                                              fetchDashboardAndConfig();
                                            } catch (err) {
                                              alert("Failed to update verification check: " + err.message);
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
                                  onClick={async () => {
                                    const commentVal = document.getElementById(`comments-${order.id}`).value;
                                    const fileInput = document.getElementById(`image-${order.id}`);
                                    const file = fileInput.files[0];
                                    
                                    try {
                                      await api.submitCompletion(order.id, commentVal, file);
                                      alert("Completion report submitted successfully!");
                                      fetchDashboardAndConfig();
                                    } catch (err) {
                                      alert("Submission failed: " + err.message);
                                    }
                                  }}
                                >
                                  Submit & Send for Quality Check
                                </button>
                              </div>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}

            {dashboardTab === 'overview' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        {t('dashboard.welcomeBackUser', `Welcome back, ${currentUserName}! 👋`, { name: currentUserName })}
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{t('dashboard.subtitle')}</p>
                    </div>
                  </div>
                  <div className="portal-header-right" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <button className="btn-primary" onClick={() => setView('order-selector')}>
                      <Sparkles size={16} />
                      {t('dashboard.newOrder')}
                    </button>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  </div>
                </header>

                {/* Quick Action Grid */}
                <section className="quick-action-button-grid">
                  <div className="quick-action-item" onClick={() => setView('order-selector')}>
                    <div className="quick-action-icon-box"><ShoppingBag size={18} /></div>
                    <h4>{t('dashboard.newOrder')}</h4>
                    <p>{t('dashboard.startCustomOrder', 'Start custom order')}</p>
                  </div>
                  <div className="quick-action-item" onClick={() => setDashboardTab('tailors')}>
                    <div className="quick-action-icon-box"><Scissors size={18} /></div>
                    <h4>{t('dashboard.manageStaff', 'Manage Staff')}</h4>
                    <p>{t('dashboard.tailorsStatus', 'Tailors & status')}</p>
                  </div>
                  <div className="quick-action-item" onClick={() => setDashboardTab('designs')}>
                    <div className="quick-action-icon-box"><Heart size={18} /></div>
                    <h4>{t('dashboard.designCatalog', 'Design Catalog')}</h4>
                    <p>{t('dashboard.styleCollections', 'Style collections')}</p>
                  </div>
                  <div className="quick-action-item" onClick={() => setDashboardTab('fabrics')}>
                    <div className="quick-action-icon-box"><Compass size={18} /></div>
                    <h4>{t('dashboard.fabricLibrary', 'Fabric Library')}</h4>
                    <p>{t('dashboard.exploreFabrics', 'Explore fabrics')}</p>
                  </div>
                  <div className="quick-action-item" onClick={() => setShowAppointmentModal(true)}>
                    <div className="quick-action-icon-box"><Calendar size={18} /></div>
                    <h4>{t('dashboard.bookAppointment', 'Book Appointment')}</h4>
                    <p>{t('dashboard.consultStylist', 'Consult with stylist')}</p>
                  </div>
                </section>

                {/* Row Layout: Orders & Progress Tracker */}
                <div className="dashboard-row-layout">
                  {/* Active Orders List */}
                  <div className="orders-list-panel">
                    <div className="panel-header-row">
                      <h3 style={{ fontSize: '16px', fontWeight: 600 }}>{t('dashboard.myOrders', 'My Orders')}</h3>
                      <a className="view-all-link" style={{ cursor: 'pointer' }} onClick={() => setDashboardTab('orders')}>{t('dashboard.viewAllOrders', 'VIEW ALL ORDERS →')}</a>
                    </div>


                    {loading ? (
                      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                        Loading active orders...
                      </div>
                    ) : !dashboardData?.recent_orders || dashboardData.recent_orders.length === 0 ? (
                      <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No active custom orders. Click "New Custom Order" to begin!
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        {dashboardData.recent_orders.map(order => (
                          <div 
                            key={order.id} 
                            className={`order-row-card ${selectedDashboardOrder?.id === order.id ? 'active-border' : ''}`}
                            onClick={() => setSelectedDashboardOrder(order)}
                            style={{
                              borderColor: selectedDashboardOrder?.id === order.id ? 'var(--text-primary)' : 'var(--border-color)'
                            }}
                          >
                            <div className="order-row-thumbnail">
                              <img 
                                src="https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=100" 
                                alt="Garment Thumbnail" 
                              />
                            </div>
                            <div className="order-row-desc">
                              <div className="order-row-id">{t('dashboard.orderId', 'Order ID:')} {order.order_id}</div>
                              <div className="order-row-name">{order.customer_name} • {order.order_status_display || t(`status.${order.order_status}`, order.order_status)}</div>
                              <div className="order-row-fabric">{t('ordersPage.stitchingTailor', 'Tailor')}: {order.tailor_name || t('ordersPage.unassigned', 'Unassigned')}</div>
                            </div>
                            <div className="order-row-status-box">
                              {/* Show the status the order is actually in. This
                                  used to be a two-way test -- 'Confirmed', or
                                  else the words "In Progress" -- so a dress that
                                  had been finished, shipped and handed over
                                  still read "In Progress" on the owner's
                                  dashboard, directly beside the word Delivered.
                                  Green for the settled states, amber while the
                                  garment is still moving. */}
                              <span className={`order-row-badge ${['Confirmed', 'Shipped', 'Delivered'].includes(order.order_status) ? 'confirmed' : 'in_progress'}`}>
                                {order.order_status_display || t(`status.${order.order_status}`, order.order_status || 'In Progress')}
                              </span>
                              <span className="order-row-date">{t('ordersPage.estDelivery', 'Est.')} {new Date(order.estimated_delivery).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Order Live Tracker Sidebar */}
                  <div className="order-detail-progress-card">
                    <div className="panel-header-row">
                      <h3 style={{ fontSize: '15px', fontWeight: 600 }}>{t('dashboard.orderProgress', 'Order Progress')}</h3>
                      <a className="view-all-link" style={{ cursor: 'pointer' }} onClick={() => setDashboardTab('orders')}>{t('dashboard.viewAll', 'VIEW ALL')}</a>
                    </div>

                    {selectedDashboardOrder ? (
                      <>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <div style={{ fontSize: '13px', fontWeight: 600 }}>{selectedDashboardOrder.customer_name}</div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{t('dashboard.orderId', 'Order ID:')} {selectedDashboardOrder.order_id}</div>
                        </div>

                        <div style={{ marginTop: '12px', marginBottom: '16px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontWeight: 600, marginBottom: '4px' }}>
                            <span>{t('dashboard.productionProgress', 'PRODUCTION PROGRESS')}</span>
                            <span>{(() => {
                              const stages = selectedDashboardOrder.stages || [];
                              const completed = stages.filter(s => s.status === 'COMPLETED').length;
                              const pct = stages.length > 0 ? Math.round((completed / stages.length) * 100) : 0;
                              return `${pct}% (${completed}/${stages.length} ${t('dashboard.stages', 'Stages')})`;
                            })()}</span>
                          </div>
                          <div style={{ height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden' }}>
                            <div style={{
                              height: '100%',
                              width: `${(() => {
                                const stages = selectedDashboardOrder.stages || [];
                                const completed = stages.filter(s => s.status === 'COMPLETED').length;
                                return stages.length > 0 ? Math.round((completed / stages.length) * 100) : 0;
                              })()}%`,
                              background: 'linear-gradient(90deg, #d4af37, #b07c40)',
                              transition: 'width 0.3s ease'
                            }}></div>
                          </div>
                        </div>

                        <div className="order-progress-steps-list" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                          {(() => {
                            const stages = selectedDashboardOrder.stages || [];
                            return stages.map((stage, idx) => {
                              const isCompleted = stage.status === 'COMPLETED';
                              const isInProgress = stage.status === 'IN_PROGRESS';
                              const isPaused = stage.status === 'PAUSED';
                              const isSkipped = stage.status === 'SKIPPED';
                              
                              let statusColor = '#555'; // NOT_STARTED
                              let statusText = 'Not Started';
                              if (isCompleted) { statusColor = '#10b981'; statusText = 'Completed'; }
                              else if (isInProgress) { statusColor = '#3b82f6'; statusText = 'In Progress'; }
                              else if (isPaused) { statusColor = '#f59e0b'; statusText = 'Paused'; }
                              else if (isSkipped) { statusColor = '#9ca3af'; statusText = 'Skipped'; }
                              
                              return (
                                <div 
                                  key={stage.id || stage.stage_key} 
                                  className={`progress-step-item ${isCompleted ? 'completed' : isInProgress ? 'active' : ''}`}
                                  style={{
                                    cursor: 'pointer',
                                    padding: '10px 12px',
                                    borderRadius: '8px',
                                    border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
                                    background: isInProgress ? 'rgba(59, 130, 246, 0.05)' : 'rgba(255,255,255,0.01)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    margin: 0
                                  }}
                                  onClick={() => {
                                    setActiveReviewStage(stage.stage_name);
                                    setActiveReviewOrder(selectedDashboardOrder);
                                    setSelectedStageObj(stage);
                                    setStageReviewComments(stage.comments || '');
                                    setStageReviewImage(null);
                                  }}
                                >
                                  <div className="progress-step-dot" style={{ backgroundColor: statusColor, width: '8px', height: '8px', borderRadius: '50%', flexShrink: 0 }}></div>
                                  <div className="progress-step-info" style={{ flex: 1, marginLeft: '12px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                      <span className="progress-step-title" style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>{stage.stage_name}</span>
                                      <span style={{
                                        fontSize: '8px',
                                        padding: '1px 5px',
                                        borderRadius: '3px',
                                        backgroundColor: `${statusColor}1c`,
                                        color: statusColor,
                                        fontWeight: 700
                                      }}>{statusText.toUpperCase()}</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-muted)' }}>
                                      <span>{stage.performed_by_name ? `By: ${stage.performed_by_name}` : ''}</span>
                                      <span>
                                        {stage.completed_at ? new Date(stage.completed_at).toLocaleDateString(undefined, {day: 'numeric', month: 'short'}) :
                                         stage.started_at ? `Started: ${new Date(stage.started_at).toLocaleDateString(undefined, {day: 'numeric', month: 'short'})}` : ''}
                                      </span>
                                    </div>

                                    {/* Who should do this stage, ahead of the work starting.
                                        Only staff whose role the stage permits are offered. */}
                                    {!isCompleted && currentUser.role === 'Owner' && (
                                      <div
                                        style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}
                                        onClick={e => e.stopPropagation()}
                                      >
                                        <span style={{ fontSize: '10px', color: 'var(--text-muted)', flexShrink: 0 }}>{t('dashboard.assign', 'Assign:')}</span>
                                        <select
                                          className="form-control"
                                          style={{ fontSize: '10px', padding: '2px 4px', height: 'auto' }}
                                          value={stage.assigned_to || ''}
                                          disabled={assigningStageKey === stage.stage_key}
                                          onChange={e => handleAssignStage(
                                            selectedDashboardOrder.id, stage.stage_key, e.target.value
                                          )}
                                        >
                                          <option value="">{t('ordersPage.unassigned', 'Unassigned')}</option>
                                          {eligibleStaffForStage(stage.stage_key).map(t => (
                                            <option key={t.id} value={t.id}>{t.name} · {t.role}</option>
                                          ))}
                                        </select>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              );
                            });
                          })()}
                        </div>

                        {/* Delivery Information */}
                        <div style={{ marginTop: '16px', background: 'rgba(0,0,0,0.02)', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '12px' }}>
                          <div style={{ fontWeight: 600, marginBottom: '4px' }}>{t('ordersPage.deliveryMethodLabel', 'Delivery Method:')} {selectedDashboardOrder.delivery_method_display || t(`deliveryMethod.${selectedDashboardOrder.delivery_method}`, selectedDashboardOrder.delivery_method)}</div>
                          {selectedDashboardOrder.delivery_method === 'Courier' && (
                            <div style={{ color: 'var(--text-secondary)' }}>
                              <strong>Carrier:</strong> {selectedDashboardOrder.courier_service || 'TBD'}<br />
                              <strong>Tracking:</strong> {selectedDashboardOrder.tracking_number || 'TBD'}<br />
                              {selectedDashboardOrder.delivery_address && (
                                <div style={{ marginTop: '4px', whiteSpace: 'pre-line' }}><strong>Address:</strong> {selectedDashboardOrder.delivery_address}</div>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Tailor Stitching Completion details */}
                        {(selectedDashboardOrder.tailor_comments || selectedDashboardOrder.completed_garment_image) && (
                          <div style={{
                            marginTop: '12px',
                            background: 'rgba(212,175,55,0.02)',
                            border: '1px solid rgba(212,175,55,0.15)',
                            borderRadius: '8px',
                            padding: '12px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px',
                            fontSize: '12px'
                          }}>
                            <div style={{ fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <Scissors size={12} style={{ color: 'var(--accent-text, #b07c40)' }} />
                              <span>{t('dashboard.tailorNotes', 'Tailor Completion Notes')}</span>
                            </div>
                            {selectedDashboardOrder.tailor_comments && (
                              <p style={{ color: 'var(--text-secondary)', margin: 0, fontStyle: 'italic' }}>
                                "{selectedDashboardOrder.tailor_comments}"
                              </p>
                            )}
                            {selectedDashboardOrder.completed_garment_image && (
                              <div style={{ marginTop: '2px' }}>
                                <a href={selectedDashboardOrder.completed_garment_image} target="_blank" rel="noreferrer">
                                  <img 
                                    src={selectedDashboardOrder.completed_garment_image} 
                                    alt="Completed Garment" 
                                    style={{
                                      width: '80px',
                                      height: '80px',
                                      objectFit: 'cover',
                                      borderRadius: '4px',
                                      border: '1px solid var(--border-color)'
                                    }} 
                                  />
                                </a>
                              </div>
                            )}
                          </div>
                        )}

                        <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px solid var(--border-color, rgba(255,255,255,0.08))', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontSize: '12px', fontWeight: 600 }}>{t('ordersPage.updateStatus', 'Update Status:')}</span>
                            <select 
                              value={selectedDashboardOrder.order_status} 
                              onChange={async (e) => {
                                const newStatus = e.target.value;
                                try {
                                  await api.updateOrderStatus(selectedDashboardOrder.id, newStatus);
                                  setSelectedDashboardOrder(prev => ({ ...prev, order_status: newStatus }));
                                  fetchDashboardAndConfig();
                                } catch (err) {
                                  alert("Failed to update status: " + err.message);
                                }
                              }}
                              style={{
                                background: 'rgba(255,255,255,0.05)',
                                color: 'var(--text-primary)',
                                border: '1px solid rgba(255,255,255,0.15)',
                                borderRadius: '6px',
                                padding: '4px 8px',
                                fontSize: '12px',
                                cursor: 'pointer'
                              }}
                            >
                              {['Received', 'Confirmed', 'Stylist Review', 'Design & Creation', 'Quality Check', 'Ready for Dispatch', 'Shipped', 'Delivered'].map(status => (
                                <option key={status} value={status} style={{ background: '#222', color: '#fff' }}>{t(`status.${status}`, status)}</option>
                              ))}
                            </select>
                          </div>
                          
                          {selectedDashboardOrder.order_status !== 'Delivered' && (
                            <button 
                              className="btn-primary" 
                              style={{ fontSize: '12px', padding: '8px 12px', justifyContent: 'center', width: '100%' }}
                              onClick={async () => {
                                const stages = ['Received', 'Confirmed', 'Stylist Review', 'Design & Creation', 'Quality Check', 'Ready for Dispatch', 'Shipped', 'Delivered'];
                                const currentIndex = stages.indexOf(selectedDashboardOrder.order_status);
                                if (currentIndex !== -1 && currentIndex < stages.length - 1) {
                                  const nextStatus = stages[currentIndex + 1];
                                  try {
                                    await api.updateOrderStatus(selectedDashboardOrder.id, nextStatus);
                                    setSelectedDashboardOrder(prev => ({ ...prev, order_status: nextStatus }));
                                    fetchDashboardAndConfig();
                                  } catch (err) {
                                    alert("Failed to update status: " + err.message);
                                  }
                                }
                              }}
                            >
                              {t('dashboard.advanceStage', 'Advance to Next Stage')}
                            </button>
                          )}
                        </div>
                      </>
                    ) : (
                      <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '12px' }}>
                        {t('dashboard.selectOrderHint', 'Select an order on the left to see progress details.')}
                      </div>
                    )}
                  </div>
                </div>

                {/* Upcoming Appointments & Style Inspiration Row */}
                <div className="dashboard-row-layout">
                  <div>
                    <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>{t('dashboard.upcomingAppointments', 'Upcoming Appointments')}</h3>
                    {/* Real appointments. These were two literal cards naming
                        "Anya (Stylist)" and "Rohit (Master Tailor)" on fixed
                        dates -- shown to every boutique including one created
                        a minute ago, whose owner has no such staff and no such
                        bookings. apps/scheduling has always been able to
                        answer this; nothing had ever asked it. An empty panel
                        is better than an invented one. */}
                    <div className="appointments-section-panel">
                      {appointments.length === 0 ? (
                        <div style={{ padding: '16px', fontSize: '12.5px', color: 'var(--text-muted)' }}>
                          {t('dashboard.noAppointments', 'No appointments booked.')}
                        </div>
                      ) : appointments.map(appt => {
                        const when = new Date(appt.scheduled_time);
                        return (
                          <div className="appt-card" key={appt.id}>
                            <div className="appt-date-box">
                              <span className="appt-day">{when.toLocaleDateString(undefined, { day: '2-digit' })}</span>
                              <span className="appt-month">{when.toLocaleDateString(undefined, { month: 'short' })}</span>
                            </div>
                            <div className="appt-info">
                              <span className="appt-title">
                                {APPOINTMENT_TYPE_LABELS[appt.appointment_type] || t('dashboard.appointment', 'Appointment')}
                              </span>
                              <span className="appt-sub">
                                {appt.customer_detail
                                  ? `${appt.customer_detail.first_name} ${appt.customer_detail.last_name}`
                                  : t('ordersPage.client', 'Client')}
                                {appt.assigned_staff_detail ? t('dashboard.withStaff', ' · with {name}', { name: appt.assigned_staff_detail.name }) : ''}
                              </span>
                              <span className="appt-time">
                                {when.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* "Style Inspiration" was three hardcoded Unsplash
                      portraits of strangers with no behaviour and no
                      relationship to this boutique's work -- stock photography
                      presented on the owner's own dashboard as if it were
                      theirs. Deleted rather than repointed at real designs: the
                      Design Catalogue quick-action above already goes there,
                      and a second silent route to the same screen is not worth
                      a panel. */}
                </div>
              </>
            )}

            {/* INVENTORY TAB */}
            {dashboardTab === 'inventory' && (
              <Suspense fallback={<ScreenLoading />}>
                <InventoryPanel currentUser={currentUser} />
              </Suspense>
            )}

            {/* 2. MANAGE FABRICS TAB */}
            {dashboardTab === 'fabrics' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        {t('fabricsPage.title')}
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{t('fabricsPage.subtitle')}</p>
                    </div>
                  </div>
                  <div className="portal-header-right" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <button className="btn-primary" onClick={() => {
                      setEditingFabric(null);
                      setFabricForm({ name: '', material: '', color: '', price_per_meter: '', image_url: '', is_available: true });
                      setShowFabricModal(true);
                    }}>
                      <Plus size={16} />
                      {t('fabricsPage.addNewFabric')}
                    </button>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  </div>
                </header>


                <div className="fabric-manager-content" style={{ marginTop: '24px' }}>
                  <div className="fabrics-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '24px' }}>
                    {fabrics.map(fabric => (
                      <div key={fabric.id} className="fabric-manage-card" style={{
                        background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                        border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                        borderRadius: '12px',
                        padding: '16px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        gap: '16px'
                      }}>
                        <div style={{ display: 'flex', gap: '16px' }}>
                          <div className="fabric-image-swatch" style={{
                            width: '80px',
                            height: '80px',
                            borderRadius: '8px',
                            overflow: 'hidden',
                            background: fabric.color ? fabric.color.toLowerCase() : '#ccc',
                            flexShrink: 0,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            border: '1px solid rgba(255,255,255,0.1)'
                          }}>
                            {fabric.image_url ? (
                              <img src={resolveMediaUrl(fabric.image_url)} alt={fabric.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            ) : (
                              <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#fff', fontWeight: 600, textShadow: '1px 1px 2px rgba(0,0,0,0.5)' }}>
                                {fabric.color}
                              </span>
                            )}
                          </div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            <h4 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>{fabric.name}</h4>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Material: {fabric.material}</span>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Color: {fabric.color}</span>
                            <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--accent-text, #b07c40)', marginTop: '4px' }}>
                              {formatMoney(fabric.price_per_meter)}/mtr
                            </span>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '12px' }}>
                          <span className={`order-row-badge ${fabric.is_available ? 'confirmed' : 'in_progress'}`} style={{ fontSize: '11px', padding: '2px 8px' }}>
                            {fabric.is_available ? 'Available' : 'Out of Stock'}
                          </span>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => {
                              setEditingFabric(fabric);
                              setFabricForm({
                                name: fabric.name,
                                material: fabric.material,
                                color: fabric.color,
                                price_per_meter: fabric.price_per_meter.toString(),
                                image_url: fabric.image_url || '',
                                is_available: fabric.is_available
                              });
                              setShowFabricModal(true);
                            }}>
                              <Edit2 size={12} /> Edit
                            </button>
                            <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px', color: '#ff4d4d', borderColor: 'rgba(255,77,77,0.2)' }} onClick={() => handleDeleteFabric(fabric.id)}>
                              <Trash2 size={12} /> Delete
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* 3. MANAGE TAILORS TAB */}
            {dashboardTab === 'tailors' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        {t('tailorsPage.title')}
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{t('tailorsPage.subtitle')}</p>
                    </div>
                  </div>
                  <div className="portal-header-right" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <button className="btn-primary" onClick={() => {
                      setEditingTailor(null);
                      setTailorForm({ name: '', email: '', specialty: '', rating: 5.0, status: 'Available', role: 'Tailor' });
                      setShowTailorModal(true);
                    }}>
                      <Plus size={16} />
                      {t('tailorsPage.addNewTailor')}
                    </button>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  </div>
                </header>


                <div className="tailor-manager-content" style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '32px' }}>
                  {/* Two separate panels for Master and Stitching staff */}
                  <div className="responsive-profile-grid" style={{ gap: '24px' }}>
                    
                    {/* Master Tailors Column */}
                    <div style={{
                      background: 'var(--surface-color)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '12px',
                      padding: '24px'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
                        <Scissors size={20} style={{ color: 'var(--accent-text, #b07c40)' }} />
                        <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>{t('tailorsPage.masterTailorsCategory', 'Master Tailors (Cutting & Supervision)')}</h3>
                      </div>
                      
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {tailors.filter(t => t.role === 'Master').length === 0 ? (
                          <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>{t('tailorsPage.noMasterTailors', 'No Master Tailors registered yet.')}</p>
                        ) : (
                          tailors.filter(t => t.role === 'Master').map(tailor => (
                            <div key={tailor.id} style={{
                              background: 'rgba(0,0,0,0.015)',
                              border: '1px solid var(--border-color)',
                              borderRadius: '8px',
                              padding: '16px',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center'
                            }}>
                              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                                <div style={{ width: '40px', height: '40px', borderRadius: '50%', overflow: 'hidden' }}>
                                  <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(tailor.name)}`} alt="Avatar" style={{ width: '100%', height: '100%' }} />
                                </div>
                                <div>
                                  <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>{tailor.name}</div>
                                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{tailor.specialty}</div>
                                </div>
                              </div>
                              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                <span className={`order-row-badge ${tailor.status === 'Available' ? 'confirmed' : 'in_progress'}`} style={{ fontSize: '11px', padding: '2px 8px' }}>
                                  {tailor.status === 'Available' ? t('tailorsPage.available', 'Available') : t('tailorsPage.busy', 'Busy')}
                                </span>
                                <button className="btn-secondary" style={{ padding: '6px 10px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }} onClick={() => {
                                  if (!tailor.email) {
                                    alert("Please edit this tailor's profile to add their email address first.");
                                    return;
                                  }
                                  setShareCredsTailor(tailor);
                                }}>
                                  <Lock size={12} /> {t('tailorsPage.shareBtn', 'Share')}
                                </button>
                                <button className="btn-secondary" style={{ padding: '6px 10px', fontSize: '11px' }} onClick={() => {
                                  setEditingTailor(tailor);
                                  setTailorForm({
                                    name: tailor.name,
                                    email: tailor.email || '',
                                    specialty: tailor.specialty,
                                    rating: tailor.rating.toString(),
                                    status: tailor.status,
                                    role: tailor.role || 'Tailor'
                                  });
                                  setShowTailorModal(true);
                                }}>{t('tailorsPage.editBtn', 'Edit')}</button>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    {/* Stitching Tailors Column */}
                    <div style={{
                      background: 'var(--surface-color)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '12px',
                      padding: '24px'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
                        <Scissors size={20} />
                        <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>{t('tailorsPage.stitchingTailorsCategory', 'Stitching Tailors (Assembly & Detailing)')}</h3>
                      </div>
                      
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {stitchingStaff().length === 0 ? (
                          <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>{t('tailorsPage.noStitchingTailors', 'No Stitching Tailors registered yet.')}</p>
                        ) : (
                          stitchingStaff().map(tailor => (
                            <div key={tailor.id} style={{
                              background: 'rgba(0,0,0,0.015)',
                              border: '1px solid var(--border-color)',
                              borderRadius: '8px',
                              padding: '16px',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center'
                            }}>
                              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                                <div style={{ width: '40px', height: '40px', borderRadius: '50%', overflow: 'hidden' }}>
                                  <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(tailor.name)}`} alt="Avatar" style={{ width: '100%', height: '100%' }} />
                                </div>
                                <div>
                                  <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>{tailor.name}</div>
                                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{tailor.specialty}</div>
                                </div>
                              </div>
                              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                <span className={`order-row-badge ${tailor.status === 'Available' ? 'confirmed' : 'in_progress'}`} style={{ fontSize: '11px', padding: '2px 8px' }}>
                                  {tailor.status === 'Available' ? t('tailorsPage.available', 'Available') : t('tailorsPage.busy', 'Busy')}
                                </span>
                                <button className="btn-secondary" style={{ padding: '6px 10px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }} onClick={() => {
                                  if (!tailor.email) {
                                    alert("Please edit this tailor's profile to add their email address first.");
                                    return;
                                  }
                                  setShareCredsTailor(tailor);
                                }}>
                                  <Lock size={12} /> {t('tailorsPage.shareBtn', 'Share')}
                                </button>
                                <button className="btn-secondary" style={{ padding: '6px 10px', fontSize: '11px' }} onClick={() => {
                                  setEditingTailor(tailor);
                                  setTailorForm({
                                    name: tailor.name,
                                    email: tailor.email || '',
                                    specialty: tailor.specialty,
                                    rating: tailor.rating.toString(),
                                    status: tailor.status,
                                    role: tailor.role || 'Tailor'
                                  });
                                  setShowTailorModal(true);
                                }}>{t('tailorsPage.editBtn', 'Edit')}</button>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                  </div>

                  {/* Boutique Workflow Supervision Table */}
                  <div style={{
                    background: 'var(--surface-color)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '12px',
                    padding: '24px'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
                      <Sparkles size={20} style={{ color: 'var(--accent-text, #b07c40)' }} />
                      <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>{t('tailorsPage.workflowSupervisionTitle', 'Workflow Assignment & Supervision Control')}</h3>
                    </div>
                    
                    <div style={{ overflowX: 'auto' }}>
                      <table className="portal-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ textAlign: 'left', borderBottom: '1.5px solid var(--border-color)' }}>
                            <th style={{ padding: '12px 16px', fontSize: '13px', fontWeight: 600 }}>{t('tailorsPage.colOrderClient', 'Order / Client')}</th>
                            <th style={{ padding: '12px 16px', fontSize: '13px', fontWeight: 600 }}>{t('common.status', 'Status')}</th>
                            <th style={{ padding: '12px 16px', fontSize: '13px', fontWeight: 600 }}>{t('tailorsPage.supervisingMaster', 'Supervising Master')}</th>
                            <th style={{ padding: '12px 16px', fontSize: '13px', fontWeight: 600 }}>{t('tailorsPage.stitchingTailor', 'Stitching Tailor')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {ordersList.filter(o => ['Received', 'Confirmed', 'Stylist Review', 'Design & Creation', 'Quality Check', 'Ready for Dispatch', 'Shipped'].includes(o.order_status)).length === 0 ? (
                            <tr>
                              <td colSpan="4" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                                {t('tailorsPage.noActiveOrdersInCreation', 'No active orders in creation phase.')}
                              </td>
                            </tr>
                          ) : (
                            ordersList.filter(o => ['Received', 'Confirmed', 'Stylist Review', 'Design & Creation', 'Quality Check', 'Ready for Dispatch', 'Shipped'].includes(o.order_status)).map(order => (
                              <tr key={order.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                                <td style={{ padding: '16px', fontSize: '14px' }}>
                                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{order.order_id}</div>
                                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{order.customer_name}</div>
                                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px', fontStyle: 'italic' }}>
                                    {order.delivery_method} {order.delivery_method === 'Courier' && `(${order.courier_service || 'TBD'})`}
                                  </div>
                                </td>
                                <td style={{ padding: '16px' }}>
                                  <span className={`order-row-badge ${order.order_status.toLowerCase().replace(/ & /g, '_').replace(/ /g, '_')}`} style={{ fontSize: '11px', padding: '2px 8px' }}>
                                    {t(`status.${order.order_status}`, order.order_status)}
                                  </span>
                                </td>
                                <td style={{ padding: '16px' }}>
                                  <select 
                                    className="form-control"
                                    style={{ fontSize: '13px', padding: '6px 12px', width: '200px' }}
                                    value={order.master || ''}
                                    onChange={(e) => handleAssignWorkflow(order.id, { master: e.target.value || null })}
                                  >
                                    <option value="">{t('ordersPage.unassigned', 'Unassigned')}</option>
                                    {tailors.filter(t => t.role === 'Master').map(m => (
                                      <option key={m.id} value={m.id}>{m.name}</option>
                                    ))}
                                  </select>
                                </td>
                                <td style={{ padding: '16px' }}>
                                  <select 
                                    className="form-control"
                                    style={{ fontSize: '13px', padding: '6px 12px', width: '200px' }}
                                    value={order.tailor || ''}
                                    onChange={(e) => handleAssignWorkflow(order.id, { tailor: e.target.value || null })}
                                  >
                                    <option value="">{t('ordersPage.unassigned', 'Unassigned')}</option>
                                    {stitchingStaff().map(s => (
                                      <option key={s.id} value={s.id}>{s.name}</option>
                                    ))}
                                  </select>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                </div>
              </>
            )}

            {/* 4b. DESIGN WORK TAB -- assign, submit, review. One component for
                 both ends of the loop; see features/designStudio/DesignWork. */}
            {dashboardTab === 'designWork' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        {t('designWorkPage.title', 'Design Work')}
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                        {currentUser?.role === 'Designer'
                          ? t('designWorkPage.subtitleDesigner', 'The garments you have been asked to design.')
                          : t('designWorkPage.subtitleSupervisor', 'Assign a garment to a designer, and review what comes back.')}
                      </p>
                    </div>
                  </div>
                </header>
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
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        {t('designsPage.title')}
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{t('designsPage.subtitle')}</p>
                    </div>
                  </div>
                  <div className="portal-header-right" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {(!currentUser?.role || currentUser.role === 'Owner') && (
                      <button className="btn-primary" onClick={() => {
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
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  </div>
                </header>


                <div className="design-manager-content" style={{ marginTop: '24px' }}>
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
                            description: design.description || ''
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
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        {t('ordersPage.title')}
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                        {t('ordersPage.subtitle')}
                      </p>
                    </div>
                  </div>
                  <div className="portal-header-right" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {(!currentUser?.role || currentUser.role === 'Owner') && (
                      <button className="btn-primary" onClick={handleStartNewCustomer}>
                        <Plus size={16} /> {t('ordersPage.newOrder')}
                      </button>
                    )}
                  </div>
                </header>

                <div className="orders-registry-content" style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {/* Filters & Search */}
                  <div style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '16px',
                    background: 'var(--surface-color)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '12px',
                    padding: '16px'
                  }}>
                    {/* Filter Tabs. Wrapping, not nowrap: four pills do not fit
                        one 320px row and "Delivered" was clipped off the end. */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                      {[
                        { key: 'All', label: t('ordersPage.filterAll') },
                        { key: 'Active', label: t('ordersPage.filterActive') },
                        { key: 'Shipped', label: t('ordersPage.filterShipped') },
                        { key: 'Delivered', label: t('ordersPage.filterDelivered') }
                      ].map(({ key: statusTab, label }) => (
                        <button 
                          key={statusTab}
                          onClick={() => setOrdersFilterTab(statusTab)}
                          className={ordersFilterTab === statusTab ? 'btn-primary' : 'btn-secondary'}
                          style={{ padding: '6px 16px', fontSize: '13px' }}
                        >
                          {label}
                        </button>
                      ))}
                    </div>

                    {/* Search Input */}
                    <div className="search-bar-container" style={{ width: '100%', maxWidth: '300px', margin: 0 }}>
                      <Search className="search-icon" size={16} />
                      <input 
                        type="text" 
                        placeholder={t('ordersPage.searchPlaceholder')}
                        className="search-input"
                        value={ordersSearch}
                        onChange={(e) => setOrdersSearch(e.target.value)}
                      />
                    </div>
                  </div>


                  {/* Orders List Grid */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {(() => {
                      const filtered = ordersList.filter(order => {
                        // Status filter
                        if (ordersFilterTab === 'Active') {
                          if (['Shipped', 'Delivered'].includes(order.order_status)) return false;
                        } else if (ordersFilterTab === 'Shipped') {
                          if (order.order_status !== 'Shipped') return false;
                        } else if (ordersFilterTab === 'Delivered') {
                          if (order.order_status !== 'Delivered') return false;
                        }

                        // Search text filter
                        if (ordersSearch.trim()) {
                          const query = ordersSearch.toLowerCase();
                          const matchesId = order.order_id.toLowerCase().includes(query);
                          const matchesClient = (order.customer_name || '').toLowerCase().includes(query);
                          return matchesId || matchesClient;
                        }

                        return true;
                      });

                      if (filtered.length === 0) {
                        return (
                          <div style={{
                            background: 'var(--surface-color)',
                            border: '1px solid var(--border-color)',
                            borderRadius: '12px',
                            padding: '40px',
                            textAlign: 'center',
                            color: 'var(--text-muted)'
                          }}>
                            {/* Distinguish "no results for your filters" from
                                "you have not made an order yet". On day one no
                                filter is set and there is nothing to filter, so
                                telling a new owner their filters matched
                                nothing is both wrong and a dead end. The
                                dashboard's own orders panel already gets this
                                right. */}
                            {ordersList.length === 0 ? (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center' }}>
                                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{t('ordersPage.noOrdersYet', 'No orders yet')}</div>
                                <div style={{ fontSize: '13px', maxWidth: '44ch', lineHeight: 1.5 }}>
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
                        <div key={order.id} style={{
                          background: 'var(--surface-color)',
                          border: '1px solid var(--border-color)',
                          borderRadius: '12px',
                          padding: '24px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '16px'
                        }}>
                          {/* Top Row: Order Header */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                <span style={{ fontWeight: 700, fontSize: '18px', color: 'var(--text-primary)' }}>{order.order_id}</span>
                                <span className={`order-row-badge ${order.order_status.toLowerCase().replace(/ & /g, '_').replace(/ /g, '_')}`} style={{ fontSize: '11px', padding: '3px 10px' }}>
                                  {order.order_status_display || t(`status.${order.order_status}`, order.order_status)}
                                </span>
                              </div>
                              <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                                {t('ordersPage.client', 'Client:')} <strong>{order.customer_name}</strong> | {t('ordersPage.created', 'Created:')} {fmtDate(order.order_date)}
                              </div>
                              {(() => {
                                const v = order.master_verification || {};
                                const total = 6 + (orderGarmentNames(order).includes('Saree') ? 1 : 0);
                                const checked = Object.values(v).filter(Boolean).length;
                                if (checked > 0) {
                                  return (
                                    <div style={{ fontSize: '11px', color: 'var(--accent-text, #b07c40)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'rgba(212,175,55,0.08)', padding: '2px 8px', borderRadius: '4px', marginTop: '4px' }}>
                                      <span>{t('ordersPage.masterVerified', '👑 Master Verified:')} {checked}/{total} items ({Math.round((checked/total)*100)}%)</span>
                                    </div>
                                  );
                                }
                                return null;
                              })()}
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                              <span style={{ fontSize: '13px', fontWeight: 600 }}>{t('ordersPage.updateStatus', 'Update Status:')}</span>
                              <select 
                                className="form-control"
                                style={{ fontSize: '13px', padding: '6px 12px', width: '180px', margin: 0 }}
                                value={order.order_status}
                                onChange={(e) => {
                                  api.updateOrderStatus(order.id, e.target.value)
                                    .then(() => fetchDashboardAndConfig())
                                    .catch(err => alert("Failed to update status: " + err.message));
                                }}
                              >
                                {['Received', 'Confirmed', 'Stylist Review', 'Design & Creation', 'Quality Check', 'Ready for Dispatch', 'Shipped', 'Delivered'].map(status => (
                                  <option key={status} value={status}>{t(`status.${status}`, status)}</option>
                                ))}
                              </select>
                            </div>
                          </div>

                          {/* Horizontal Progress Timeline */}
                          <StageTimeline
                            stages={order.stages}
                            onSelectStage={(stage) => openStageReview(order, stage)}
                          />

                          <GarmentGallery
                            order={order}
                            onChanged={fetchDashboardAndConfig}
                          />

                          <CustomerMessageQueue
                            orderId={order.id}
                            messages={queuedMessages.filter(m => m.order === order.id)}
                            onMarkSent={handleMarkMessageSent}
                          />

                          {/* Middle Row: Assignment & Financials */}
                          <div style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                            gap: '16px',
                            background: 'rgba(0,0,0,0.015)',
                            padding: '16px',
                            borderRadius: '8px',
                            border: '1px solid var(--border-color)'
                          }}>
                            <div>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>{t('ordersPage.supervisingMaster', 'Supervising Master')}</span>
                              <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px', color: 'var(--accent-text, #b07c40)' }}>{order.master_name || t('ordersPage.unassigned', 'Unassigned')}</div>
                            </div>
                            <div>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>{t('ordersPage.stitchingTailor', 'Stitching Tailor')}</span>
                              <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px' }}>{order.tailor_name || t('ordersPage.unassigned', 'Unassigned')}</div>
                            </div>
                            {/* The same guard the assignment card one screen
                                earlier already applies to the identical figure.
                                isProductionStaff includes 'Master', and the
                                Master's nav routes to this registry -- so the
                                one screen that was left ungated showed every
                                order's value to the roles the rule exists to
                                keep it from. Guarded here rather than by
                                popping the field from OrderSerializer, which is
                                also the read path for the invoice modal, the
                                customer tracking page and the whole registry. */}
                            {!isProductionStaff(currentUser.role) && (
                              <div>
                                <span style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>{t('ordersPage.totalValue', 'Total Value')}</span>
                                <div style={{ fontSize: '14px', fontWeight: 700, marginTop: '2px', color: 'var(--text-primary)' }}>₹{parseFloat(order.total_amount).toLocaleString()}</div>
                              </div>
                            )}
                            <div>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>{t('ordersPage.estDelivery', 'Est. Delivery')}</span>
                              <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px' }}>{order.estimated_delivery ? fmtDate(order.estimated_delivery) : t('ordersPage.tbd', 'TBD')}</div>
                            </div>
                          </div>

                          {/* Master Verification Checklist in Orders Tab */}
                          {currentUser.role === 'Master' && (
                            <div style={{
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
                                  ...(order.customer_garment_type === 'Saree' ? [{ key: 'fall_pico', label: 'Fall & Pico / Peack' }] : []),
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
                                        onChange={async (e) => {
                                          const updatedVerification = {
                                            ...(order.master_verification || {}),
                                            [item.key]: e.target.checked
                                          };
                                          try {
                                            await api.saveMasterVerification(order.id, updatedVerification);
                                            fetchDashboardAndConfig();
                                          } catch (err) {
                                            alert("Failed to update verification check: " + err.message);
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

                          {/* Bottom Row: Delivery details */}
                          <div style={{
                            background: 'rgba(0,0,0,0.01)',
                            border: '1px dashed var(--border-color)',
                            borderRadius: '8px',
                            padding: '16px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px'
                          }}>
                            <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
                              {t('ordersPage.deliveryMethodLabel', 'Delivery Method:')} {order.delivery_method_display || t(`deliveryMethod.${order.delivery_method}`, order.delivery_method)}
                            </div>
                            {order.delivery_method === 'Courier' && (
                              <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                                <div><strong>Courier Service Provider:</strong> {order.courier_service || 'TBD'}</div>
                                <div><strong>Tracking Reference:</strong> {order.tracking_number || 'TBD'}</div>
                                <div style={{ gridColumn: 'span 2', marginTop: '4px' }}>
                                  <strong>Shipping Address:</strong> {order.delivery_address || 'No address specified'}
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Tailor Stitching Completion details */}
                          {(order.tailor_comments || order.completed_garment_image) && (
                            <div style={{
                              background: 'rgba(212,175,55,0.02)',
                              border: '1px solid rgba(212,175,55,0.15)',
                              borderRadius: '8px',
                              padding: '16px',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '10px'
                            }}>
                              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <Scissors size={14} style={{ color: 'var(--accent-text, #b07c40)' }} />
                                <span>Stitching Completion Report (Tailor Feedback)</span>
                              </div>
                              {order.tailor_comments && (
                                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: 0, fontStyle: 'italic' }}>
                                  "{order.tailor_comments}"
                                </p>
                              )}
                              {order.completed_garment_image && (
                                <div style={{ marginTop: '4px' }}>
                                  <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Garment Photo:</span>
                                  <a href={order.completed_garment_image} target="_blank" rel="noreferrer">
                                    <img 
                                      src={order.completed_garment_image} 
                                      alt="Completed Garment" 
                                      style={{
                                        width: '100px',
                                        height: '100px',
                                        objectFit: 'cover',
                                        borderRadius: '6px',
                                        border: '1px solid var(--border-color)',
                                        cursor: 'pointer'
                                      }} 
                                    />
                                  </a>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ));
                    })()}
                  </div>
                </div>
              </>
            )}

            {/* 5. CUSTOMERS TAB */}
            {dashboardTab === 'customers' && !selectedDirectoryCustomer && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        {t('customersPage.title')}
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{t('customersPage.subtitle')}</p>
                    </div>
                  </div>
                  <div className="portal-header-right" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div className="search-input-wrapper" style={{ margin: 0 }}>
                      <Search size={18} />
                      <input 
                        type="text" 
                        placeholder={t('customersPage.searchPlaceholder')} 
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="form-control"
                        style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}
                      />
                    </div>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  </div>
                </header>

                {/* Customer Type Filters */}
                <div style={{ display: 'flex', gap: '12px', marginTop: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
                  {[
                    { key: 'All', label: t('customersPage.filterAll') },
                    { key: 'Women', label: t('customersPage.filterWomen') },
                    { key: 'Men', label: t('customersPage.filterMen') },
                    { key: 'Kids', label: t('customersPage.filterKids') }
                  ].map(({ key: type, label }) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => setCustomerTypeFilter(type)}
                      style={{
                        padding: '8px 16px',
                        fontSize: '13px',
                        fontWeight: 600,
                        borderRadius: '6px',
                        border: '1px solid',
                        borderColor: customerTypeFilter === type ? 'var(--accent-text, #b07c40)' : 'var(--border-color)',
                        background: customerTypeFilter === type ? 'var(--accent-color, #fcf6ee)' : 'transparent',
                        color: customerTypeFilter === type ? 'var(--accent-text, #b07c40)' : 'var(--text-secondary)',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease'
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                <div className="customers-list-container" style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {loading && customersList.length === 0 ? (
                    <div style={{ padding: '48px', textAlign: 'center', background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                      <span style={{ color: 'var(--text-muted)' }}>{t('common.loading')}</span>
                    </div>
                  ) : loadErrors.includes('customers') ? (
                    <div style={{ padding: '48px', textAlign: 'center', background: 'rgba(127,29,29,0.15)', borderRadius: '12px', border: '1px solid rgba(220,38,38,0.3)' }}>
                      <div style={{ color: '#fca5a5', marginBottom: '12px' }}>Could not load the customer directory.</div>
                      <button type="button" className="btn-secondary" onClick={() => fetchDashboardAndConfig()}>Retry</button>
                    </div>
                  ) : directoryCustomers.length === 0 ? (
                    <div style={{ padding: '48px', textAlign: 'center', background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                      {customersList.length === 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center' }}>
                          <div style={{ fontWeight: 600 }}>{t('customersPage.noCustomersYet')}</div>
                          <div style={{ fontSize: '13px', color: 'var(--text-muted)', maxWidth: '44ch', lineHeight: 1.5 }}>
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

                    directoryCustomers.map(cust => (
                      <div key={cust.id} className="customer-detail-card responsive-customer-card" style={{
                        background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                        border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                        borderRadius: '12px',
                        padding: '24px'
                      }}>
                        {/* Profile Info */}
                        <div 
                          style={{ display: 'flex', flexDirection: 'column', gap: '12px', cursor: 'pointer' }}
                          onClick={() => openDirectoryCustomer(cust)}
                        >
                          <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                            <div className="user-avatar-circle" style={{ width: '56px', height: '56px' }}>
                              <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(cust.first_name)}`} alt="Profile" />
                            </div>
                            <div>
                               <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                 <h4 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>{cust.first_name} {cust.last_name}</h4>
                                 <span style={{
                                   fontSize: '9px',
                                   fontWeight: 700,
                                   padding: '2px 6px',
                                   borderRadius: '4px',
                                   background: cust.segment === 'VIP' ? 'rgba(212, 175, 55, 0.15)' : cust.segment === 'HVC' ? 'rgba(168, 85, 247, 0.15)' : 'rgba(156, 163, 175, 0.15)',
                                   color: cust.segment === 'VIP' ? '#d4af37' : cust.segment === 'HVC' ? '#a855f7' : '#9ca3af',
                                   border: cust.segment === 'VIP' ? '1px solid rgba(212, 175, 55, 0.3)' : cust.segment === 'HVC' ? '1px solid rgba(168, 85, 247, 0.3)' : '1px solid rgba(156, 163, 175, 0.3)',
                                   textTransform: 'uppercase'
                                 }}>
                                   {cust.segment}
                                 </span>
                               </div>
                               <span style={{ fontSize: '12px', color: 'var(--accent-text, #b07c40)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.5px' }}>{cust.customer_type}</span>
                             </div>
                          </div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '13px', color: 'var(--text-secondary)', marginTop: '8px' }}>
                            <div>📞 {formatMobile(cust.mobile_number)}</div>
                            {cust.email_address && <div>✉️ {cust.email_address}</div>}
                            {cust.address && <div>📍 {cust.address}, {cust.city_region}</div>}
                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>{t('customersPage.registered')} {fmtDate(cust.created_at)}</div>
                          </div>
                        </div>

                        {/* Measurements */}
                        <div style={{ borderLeft: '1px solid rgba(255,255,255,0.05)', paddingLeft: '24px' }}>
                          <h5 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{t('customersPage.bodyMeasurements')}</h5>
                          {cust.measurements ? (
                            <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px', fontSize: '13px' }}>
                              {(() => {
                                const parts = cust.measurements.additional_measurements?.stitch_parts || [];
                                const visible = getVisibleMeasurementFields(parts);
                                return (
                                  <>
                                    {visible.includes('bust') && <div>Bust: <span style={{ fontWeight: 600 }}>{cust.measurements.bust || '—'} in</span></div>}
                                    {visible.includes('waist') && <div>Waist: <span style={{ fontWeight: 600 }}>{cust.measurements.waist || '—'} in</span></div>}
                                    {visible.includes('hips') && <div>Hips: <span style={{ fontWeight: 600 }}>{cust.measurements.hips || '—'} in</span></div>}
                                    {visible.includes('shoulder') && <div>Shoulder: <span style={{ fontWeight: 600 }}>{cust.measurements.shoulder || '—'} in</span></div>}
                                    {visible.includes('arm_length') && <div>Arm: <span style={{ fontWeight: 600 }}>{cust.measurements.arm_length || '—'} in</span></div>}
                                    {visible.includes('neck') && <div>Neck: <span style={{ fontWeight: 600 }}>{cust.measurements.neck || '—'} in</span></div>}
                                    {visible.includes('length') && <div>Length: <span style={{ fontWeight: 600 }}>{cust.measurements.length || '—'} in</span></div>}
                                  </>
                                );
                              })()}
                            </div>
                          ) : (
                            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No size measurements logged yet.</span>
                          )}
                        </div>

                        {/* Preferences */}
                        <div style={{ borderLeft: '1px solid rgba(255,255,255,0.05)', paddingLeft: '24px' }}>
                          <h5 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{t('customersPage.bespokeProfile')}</h5>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', fontSize: '12px' }}>
                            <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>{t('customersPage.garment')} {cust.garment_type}{cust.measurements?.additional_measurements?.stitch_parts?.length > 0 ? ` (${cust.measurements.additional_measurements.stitch_parts.join(', ')})` : ''}</span>
                            {cust.neckline_style && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Neck: {cust.neckline_style}</span>}
                            {cust.sleeve_style && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Sleeve: {cust.sleeve_style}</span>}
                            {cust.silhouette && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Silhouette: {cust.silhouette}</span>}
                            {cust.occasion && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>{t('customersPage.occasion')} {cust.occasion}</span>}
                          </div>
                          {cust.custom_requirements && (
                            <div style={{ marginTop: '12px' }}>
                              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Special Requests:</span>
                              <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '2px 0 0 0', lineHeight: 1.4 }}>{cust.custom_requirements}</p>
                            </div>
                          )}
                        </div>

                        {/* Style DNA Expand Button */}
                        <div style={{ gridColumn: 'span 3', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Sparkles size={16} style={{ color: 'var(--accent-text, #b07c40)' }} />
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>AI Customer Intelligence has analyzed {cust.order_count ?? cust.orders?.length ?? 0} order(s) and preferences.</span>
                          </div>
                          <button 
                            onClick={() => setExpandedDna(prev => ({ ...prev, [cust.id]: !prev[cust.id] }))}
                            style={{
                              padding: '8px 16px',
                              fontSize: '12px',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '6px',
                              border: '1px solid var(--accent-text, #b07c40)',
                              color: 'var(--accent-text, #b07c40)',
                              background: expandedDna[cust.id] ? 'var(--accent-color, #fcf6ee)' : 'transparent',
                              borderRadius: '6px',
                              cursor: 'pointer',
                              fontWeight: '600',
                              transition: 'all 0.2s ease'
                            }}
                          >
                            <Sparkles size={14} />
                            {expandedDna[cust.id] ? t('common.cancel') : t('customersPage.viewStyleDna')}
                          </button>

                        </div>

                        {/* Expandable Style DNA Section */}
                        {expandedDna[cust.id] && (
                          <div style={{
                            gridColumn: 'span 3',
                            background: '#0d0d0d',
                            border: '1px solid rgba(212, 175, 55, 0.25)',
                            borderRadius: '8px',
                            padding: '24px',
                            marginTop: '12px',
                            display: 'flex',
                            justifyContent: 'center'
                          }}>
                            {/* Left Column: Priya's Style Profile (Mockup Left Card) */}
                            <div style={{
                              background: '#141414',
                              borderRadius: '8px',
                              border: '1px solid rgba(255, 255, 255, 0.05)',
                              overflow: 'hidden',
                              width: '100%',
                              maxWidth: '550px'
                            }}>
                              {/* Title Header */}
                              <div style={{
                                background: '#e05a10',
                                padding: '12px 20px',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '10px'
                              }}>
                                <User size={18} style={{ color: '#fff' }} />
                                <span style={{
                                  color: '#fff',
                                  fontWeight: 700,
                                  fontSize: '14px',
                                  textTransform: 'uppercase',
                                  letterSpacing: '1px'
                                }}>
                                  {cust.first_name}'s Style Profile
                                </span>
                              </div>
                              
                              {/* Details Table */}
                              <div style={{ padding: '8px 20px' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                                  <tbody>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600, width: '40%' }}>BUDGET</td>
                                      <td style={{ padding: '12px 0', color: '#fff', fontWeight: 600 }}>{cust.style_dna?.budget}</td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>COLORS</td>
                                      <td style={{ padding: '12px 0', color: '#fff', fontWeight: 600 }}>
                                        {cust.style_dna?.colors.split(' ').map((word, idx) => {
                                          if (word.includes('%')) return <span key={idx} style={{ color: 'var(--text-muted)', marginRight: '12px', fontWeight: 400 }}>{word} </span>;
                                          // Color highlights
                                          let color = '#fff';
                                          if (word.toLowerCase().includes('blue')) color = '#60a5fa';
                                          else if (word.toLowerCase().includes('green')) color = '#34d399';
                                          else if (word.toLowerCase().includes('red') || word.toLowerCase().includes('maroon')) color = '#f87171';
                                          else if (word.toLowerCase().includes('gold')) color = '#fbbf24';
                                          else if (word.toLowerCase().includes('rose')) color = '#f472b6';
                                          else if (word.toLowerCase().includes('ivory') || word.toLowerCase().includes('white')) color = '#f3f4f6';
                                          else if (word.toLowerCase().includes('black') || word.toLowerCase().includes('charcoal')) color = '#9ca3af';
                                          return <span key={idx} style={{ color }}>{word} </span>;
                                        })}
                                      </td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>STYLE</td>
                                      <td style={{ padding: '12px 0', color: '#fff', fontWeight: 600 }}>{cust.style_dna?.style}</td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>SIZE</td>
                                      <td style={{ padding: '12px 0', color: '#fff', fontWeight: 600 }}>{cust.style_dna?.size}</td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>VISIT PATTERN</td>
                                      <td style={{ padding: '12px 0', color: '#fff', fontWeight: 600 }}>{cust.style_dna?.visit_pattern}</td>
                                    </tr>
                                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>RISK STATUS</td>
                                      <td style={{ padding: '12px 0', fontWeight: 600, color: cust.style_dna?.risk_level === 'danger' ? '#f87171' : cust.style_dna?.risk_level === 'warning' ? '#fbbf24' : '#34d399' }}>
                                        {cust.style_dna?.risk_status.includes('Active') ? '🟢 ' : '⚠️ '}
                                        {cust.style_dna?.risk_status}
                                      </td>
                                    </tr>
                                    <tr>
                                      <td style={{ padding: '12px 0', color: 'var(--text-muted)', fontWeight: 600 }}>NEXT ACTION</td>
                                      <td style={{ padding: '12px 0', color: 'var(--accent-text, #b07c40)', fontWeight: 600 }}>"{cust.style_dna?.next_action}"</td>
                                    </tr>
                                  </tbody>
                                </table>
                                
                                <div style={{
                                  padding: '12px 0 16px 0',
                                  fontSize: '11px',
                                  color: 'var(--text-muted)',
                                  fontStyle: 'italic',
                                  borderTop: '1px solid rgba(255,255,255,0.05)',
                                  marginTop: '8px'
                                }}>
                                  This is NOT manual entry. AI reads your sales data automatically.
                                </div>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                    ))
                  )}
                </div>
              </>
            )}

            {/* 5b. CUSTOMER DETAIL VIEW (Image 5/6 extension) */}
            {dashboardTab === 'customers' && selectedDirectoryCustomer && (
              <div className="customer-detail-view-container" style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
                {/* Back Navigation & Main Header */}
                <div className="customer-detail-header-row">
                  <button 
                    onClick={() => setSelectedDirectoryCustomer(null)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--accent-text, #b07c40)',
                      fontSize: '14px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: 0
                    }}
                  >
                    <ArrowLeft size={16} /> Back to Customer Directory
                  </button>

                  {/* Owner only, the same gate the Orders registry already
                      puts on the identical button -- and for the reason its
                      comment there records. Both of these routes land in the
                      order wizard, whose first step PATCHes the customer, and
                      RolePermission refuses partial_update for anyone but the
                      Owner. A Master reached here from the Customers tab (which
                      their nav includes), filled the form in, and got "Your
                      role does not permit this" with everything they had typed
                      thrown away and no route onward. */}
                  {(!currentUser?.role || currentUser.role === 'Owner') && (
                  <div className="customer-detail-header-actions">
                    {/* Flow Option 1: Re-use Existing Design */}
                    <button 
                      className="btn-outline" 
                      onClick={() => {
                        // Load customer and skip steps straight to design review
                        setCustomerId(selectedDirectoryCustomer.id);
                        setCustomerForm({
                          ...DEFAULT_CUSTOMER_DATA,
                          ...selectedDirectoryCustomer,
                          measurements: selectedDirectoryCustomer.measurements || DEFAULT_CUSTOMER_DATA.measurements
                        });
                        // Prefill design notes if any
                        if (selectedDirectoryCustomer.design_preferences?.length > 0) {
                          setDesignNotes(selectedDirectoryCustomer.design_preferences[0].notes || '');
                        }
                        // Set view to wizard, starting at Step 3 (Design Preferences)
                        setCurrentStep(3);
                        setView('wizard');
                      }}
                      style={{
                        padding: '10px 18px',
                        fontSize: '13px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        borderColor: 'var(--accent-text, #b07c40)',
                        color: 'var(--accent-text, #b07c40)',
                        cursor: 'pointer',
                        borderRadius: '6px',
                        background: 'transparent'
                      }}
                    >
                      <Copy size={16} />
                      Go with Existing Design
                    </button>

                    {/* Flow Option 2: Create New Design */}
                    <button 
                      className="btn-primary" 
                      onClick={() => {
                        handleSelectExistingCustomer(selectedDirectoryCustomer);
                      }}
                      style={{
                        padding: '10px 18px',
                        fontSize: '13px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        cursor: 'pointer',
                        borderRadius: '6px'
                      }}
                    >
                      <Sparkles size={16} />
                      Create New Design
                    </button>
                  </div>
                  )}
                </div>

                {/* Customer Main Banner */}
                <div className="customer-detail-banner-card">
                  <div className="user-avatar-circle" style={{ width: '80px', height: '80px', fontSize: '24px', borderRadius: '50%', overflow: 'hidden', flexShrink: 0 }}>
                    <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(selectedDirectoryCustomer.first_name)}`} alt="Profile" />
                  </div>
                   <div>
                     <div style={{ display: 'flex', alignItems: 'center', gap: '12px', margin: '0 0 6px 0' }}>
                       <h2 style={{ fontSize: '24px', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
                         {selectedDirectoryCustomer.first_name} {selectedDirectoryCustomer.last_name}
                       </h2>
                       <span style={{
                         fontSize: '11px',
                         fontWeight: 700,
                         padding: '3px 10px',
                         borderRadius: '12px',
                         background: selectedDirectoryCustomer.segment === 'VIP' ? 'rgba(212, 175, 55, 0.15)' : selectedDirectoryCustomer.segment === 'HVC' ? 'rgba(168, 85, 247, 0.15)' : 'rgba(156, 163, 175, 0.15)',
                         color: selectedDirectoryCustomer.segment === 'VIP' ? '#d4af37' : selectedDirectoryCustomer.segment === 'HVC' ? '#a855f7' : '#9ca3af',
                         border: selectedDirectoryCustomer.segment === 'VIP' ? '1px solid rgba(212, 175, 55, 0.3)' : selectedDirectoryCustomer.segment === 'HVC' ? '1px solid rgba(168, 85, 247, 0.3)' : '1px solid rgba(156, 163, 175, 0.3)',
                         textTransform: 'uppercase'
                       }}>
                         {selectedDirectoryCustomer.segment}
                       </span>
                     </div>
                    <div style={{ display: 'flex', gap: '20px', fontSize: '14px', color: 'var(--text-secondary)' }}>
                      <span>📞 {formatMobile(selectedDirectoryCustomer.mobile_number)}</span>
                      {selectedDirectoryCustomer.email_address && <span>✉️ {selectedDirectoryCustomer.email_address}</span>}
                      {selectedDirectoryCustomer.address && <span>📍 {selectedDirectoryCustomer.address}, {selectedDirectoryCustomer.city_region}</span>}
                    </div>
                  </div>
                </div>

                {/* Detailed Grid layout */}
                <div className="responsive-profile-grid">
                  
                  {/* Left Column */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                    
                    {/* Measurements & Info */}
                    <div style={{
                      background: 'var(--surface-color)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '12px',
                      padding: '24px'
                    }}>
                      <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '10px', color: 'var(--text-primary)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span>Body Measurements & Sizing</span>
                        {(() => {
                          const parts = selectedDirectoryCustomer.measurements?.additional_measurements?.stitch_parts || [];
                          return parts.length > 0 && (
                            <span style={{ fontSize: '12px', background: 'rgba(176,124,64,0.1)', color: 'var(--accent-text, #b07c40)', padding: '4px 10px', borderRadius: '4px', fontWeight: 600 }}>
                              Stitching: {parts.join(', ')}
                            </span>
                          );
                        })()}
                      </h3>
                      {selectedDirectoryCustomer.measurements ? (
                        <>
                          <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 24px', fontSize: '14px', color: 'var(--text-secondary)' }}>
                            {(() => {
                              const parts = selectedDirectoryCustomer.measurements?.additional_measurements?.stitch_parts || [];
                              const visible = getVisibleMeasurementFields(parts);
                              return (
                                <>
                                  {visible.includes('bust') && <div>Bust: <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{selectedDirectoryCustomer.measurements.bust || '—'} in</span></div>}
                                  {visible.includes('waist') && <div>Waist: <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{selectedDirectoryCustomer.measurements.waist || '—'} in</span></div>}
                                  {visible.includes('hips') && <div>Hips: <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{selectedDirectoryCustomer.measurements.hips || '—'} in</span></div>}
                                  {visible.includes('shoulder') && <div>Shoulder: <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{selectedDirectoryCustomer.measurements.shoulder || '—'} in</span></div>}
                                  {visible.includes('arm_length') && <div>Arm Length: <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{selectedDirectoryCustomer.measurements.arm_length || '—'} in</span></div>}
                                  {visible.includes('neck') && <div>Neck: <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{selectedDirectoryCustomer.measurements.neck || '—'} in</span></div>}
                                  {visible.includes('length') && <div>Length: <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{selectedDirectoryCustomer.measurements.length || '—'} in</span></div>}
                                </>
                              );
                            })()}
                            <div>Occasion Preference: <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{selectedDirectoryCustomer.occasion || '—'}</span></div>
                          </div>
                          {selectedDirectoryCustomer.measurement_history && selectedDirectoryCustomer.measurement_history.length > 0 && (
                            <div style={{ marginTop: '24px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
                              <h4 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--accent-text, #b07c40)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '6px', letterSpacing: '0.5px' }}>
                                <History size={14} /> Sizing Version History
                              </h4>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxHeight: '300px', overflowY: 'auto', paddingRight: '4px' }}>
                                {[...selectedDirectoryCustomer.measurement_history].reverse().map((hist, idx, arr) => {
                                  const dateStr = new Date(hist.changed_at).toLocaleDateString('en-US', {
                                    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                                  });
                                  const parts = selectedDirectoryCustomer.measurements?.additional_measurements?.stitch_parts || [];
                                  const visible = getVisibleMeasurementFields(parts);
                                  return (
                                    <div key={hist.id || idx} style={{
                                      background: 'rgba(0,0,0,0.015)',
                                      borderRadius: '8px',
                                      padding: '12px',
                                      borderLeft: '3px solid var(--accent-text, #b07c40)',
                                      fontSize: '12.5px'
                                    }}>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', color: 'var(--text-muted)' }}>
                                        <span style={{ fontWeight: 600 }}>Version {arr.length - idx}</span>
                                        <span>{dateStr}</span>
                                      </div>
                                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px 12px', color: 'var(--text-secondary)' }}>
                                        {visible.includes('bust') && <div>Bust: <strong style={{ color: 'var(--text-primary)' }}>{hist.bust || '—'}</strong></div>}
                                        {visible.includes('waist') && <div>Waist: <strong style={{ color: 'var(--text-primary)' }}>{hist.waist || '—'}</strong></div>}
                                        {visible.includes('hips') && <div>Hips: <strong style={{ color: 'var(--text-primary)' }}>{hist.hips || '—'}</strong></div>}
                                        {visible.includes('shoulder') && <div>Shoulder: <strong style={{ color: 'var(--text-primary)' }}>{hist.shoulder || '—'}</strong></div>}
                                        {visible.includes('arm_length') && <div>Arm: <strong style={{ color: 'var(--text-primary)' }}>{hist.arm_length || '—'}</strong></div>}
                                        {visible.includes('neck') && <div>Neck: <strong style={{ color: 'var(--text-primary)' }}>{hist.neck || '—'}</strong></div>}
                                        {visible.includes('length') && <div>Length: <strong style={{ color: 'var(--text-primary)' }}>{hist.length || '—'}</strong></div>}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </>
                      ) : (
                        <p style={{ color: 'var(--text-muted)' }}>No measurements saved yet.</p>
                      )}
                    </div>

                    {/* Order History */}
                    <div style={{
                      background: 'var(--surface-color)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '12px',
                      padding: '24px'
                    }}>
                      <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '10px', color: 'var(--text-primary)' }}>
                        Order History
                      </h3>
                      {directoryDetailLoading && !selectedDirectoryCustomer.orders ? (
                        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Loading order history…</p>
                      ) : !selectedDirectoryCustomer.orders || selectedDirectoryCustomer.orders.length === 0 ? (
                        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>No orders have been placed by this customer yet.</p>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          {selectedDirectoryCustomer.orders.map(order => {
                            // The row opens the order's production progress.
                            // It used to jump straight into the new-order
                            // wizard, so a client asking "where is my dress?"
                            // could not be answered from their own profile.
                            const isOpen = expandedCustomerOrderId === order.id;
                            const stages = order.stages || [];
                            const done = stages.filter(s => s.status === 'COMPLETED').length;
                            const current = stages.find(s => s.status === 'IN_PROGRESS');
                            return (
                            <div key={order.id} style={{
                              background: 'rgba(0,0,0,0.015)',
                              border: `1px solid ${isOpen ? 'var(--accent-text, #b07c40)' : 'var(--border-color)'}`,
                              borderRadius: '8px',
                              padding: '16px'
                            }}>
                              <div
                                onClick={() => setExpandedCustomerOrderId(isOpen ? null : order.id)}
                                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', gap: '12px' }}
                              >
                                <div>
                                  <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>Order ID: {order.order_id}</div>
                                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                                    Date: {fmtDate(order.order_date)} | Tailor: {order.tailor_name || 'Not assigned'}
                                  </div>
                                  {stages.length > 0 && (
                                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                                      Progress: {done}/{stages.length} stages
                                      {current ? ` · currently ${current.stage_name}` : ''}
                                    </div>
                                  )}
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                                  <div style={{ textAlign: 'right' }}>
                                    <div style={{ fontWeight: 700, color: 'var(--accent-text, #b07c40)', fontSize: '14px' }}>₹{parseFloat(order.total_amount).toLocaleString()}</div>
                                    <span style={{
                                      display: 'inline-block',
                                      padding: '2px 8px',
                                      borderRadius: '12px',
                                      fontSize: '11px',
                                      marginTop: '4px',
                                      background: order.order_status === 'Delivered' ? 'rgba(52, 211, 153, 0.15)' : 'rgba(251, 191, 36, 0.15)',
                                      color: order.order_status === 'Delivered' ? '#34d399' : '#fbbf24'
                                    }}>
                                      {order.order_status}
                                    </span>
                                  </div>
                                  <ChevronRight
                                    size={16}
                                    style={{ transform: isOpen ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s', color: 'var(--text-muted)' }}
                                  />
                                </div>
                              </div>

                              {isOpen && (
                                <div style={{ marginTop: '16px', borderTop: '1px dashed var(--border-color)', paddingTop: '12px' }}>
                                  <StageTimeline
                                    stages={stages}
                                    onSelectStage={(stage) => openStageReview(order, stage)}
                                  />

                                  {stages.length > 0 && (
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: '8px', marginTop: '12px' }}>
                                      {stages.map(stage => (
                                        <div key={stage.stage_key} style={{
                                          fontSize: '11px',
                                          padding: '8px 10px',
                                          borderRadius: '6px',
                                          background: 'var(--surface-color)',
                                          border: '1px solid var(--border-color)'
                                        }}>
                                          <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{stage.stage_name}</div>
                                          <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>
                                            {stage.status.replace('_', ' ').toLowerCase()}
                                            {stage.assigned_to_name ? ` · ${stage.assigned_to_name}` : ''}
                                          </div>
                                          {stage.completed_at && (
                                            <div style={{ color: 'var(--text-muted)' }}>
                                              {fmtDate(stage.completed_at)}
                                            </div>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  )}

                                  <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', fontSize: '12px', color: 'var(--text-muted)', marginTop: '12px' }}>
                                    <span>Payment: <strong style={{ color: 'var(--text-primary)' }}>{order.payment_status}</strong></span>
                                    <span>Delivery: <strong style={{ color: 'var(--text-primary)' }}>{order.delivery_method}</strong></span>
                                    {order.estimated_delivery && (
                                      <span>Expected: <strong style={{ color: 'var(--text-primary)' }}>{fmtDate(order.estimated_delivery)}</strong></span>
                                    )}
                                  </div>

                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setCustomerId(selectedDirectoryCustomer.id);
                                      setCustomerForm({
                                        ...DEFAULT_CUSTOMER_DATA,
                                        ...selectedDirectoryCustomer,
                                        measurements: selectedDirectoryCustomer.measurements || DEFAULT_CUSTOMER_DATA.measurements
                                      });
                                      // Garment prices are per garment now and
                                      // the dresses are re-added on step 3, so
                                      // they re-quote there; only the order-level
                                      // money carries over.
                                      setQuotePrices({
                                        packaging: order.packaging_handling,
                                        discount: order.discount || 0,
                                      });
                                      setCurrentStep(3);
                                      setView('wizard');
                                    }}
                                    style={{
                                      background: 'rgba(212, 175, 55, 0.1)',
                                      border: '1px solid rgba(212, 175, 55, 0.3)',
                                      color: 'var(--accent-text, #b07c40)',
                                      borderRadius: '6px',
                                      padding: '6px 12px',
                                      fontSize: '11px',
                                      cursor: 'pointer',
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: '4px',
                                      marginTop: '12px'
                                    }}
                                  >
                                    <Copy size={12} />
                                    Reorder Style
                                  </button>
                                </div>
                              )}
                            </div>
                            );
                          })}
                        </div>
                      )}
                    </div>

                  </div>

                  {/* Right Column */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                    
                    {/* Style Profile Card */}
                    <div style={{
                      background: '#141414',
                      border: '1px solid rgba(255,255,255,0.08)',
                      borderRadius: '12px',
                      overflow: 'hidden',
                      color: '#ffffff',
                      boxShadow: '0 8px 24px rgba(0,0,0,0.2)'
                    }}>
                      {/* Header */}
                      <div style={{
                        background: '#d35400',
                        backgroundImage: 'linear-gradient(135deg, #d35400, #e67e22)',
                        padding: '16px 20px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}>
                        <User size={16} style={{ color: '#fff' }} />
                        <span style={{
                          fontWeight: 700,
                          fontSize: '13px',
                          textTransform: 'uppercase',
                          letterSpacing: '1px',
                          color: '#fff'
                        }}>
                          {selectedDirectoryCustomer.first_name}'S STYLE PROFILE
                        </span>
                      </div>

                      {/* Content Rows */}
                      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '10px', fontSize: '13px' }}>
                          <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>BUDGET</span>
                          <strong style={{ color: '#fff' }}>{selectedDirectoryCustomer.style_dna?.budget || '₹26,250 (premium designer)'}</strong>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '10px', fontSize: '13px' }}>
                          <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>COLORS</span>
                          <strong style={{ color: '#fff' }}>{selectedDirectoryCustomer.style_dna?.colors || 'Charcoal Black 90% | Silver 10%'}</strong>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '10px', fontSize: '13px' }}>
                          <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>STYLE</span>
                          <strong style={{ color: '#fff' }}>{selectedDirectoryCustomer.style_dna?.style || 'Contemporary 80% | Traditional 20%'}</strong>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '10px', fontSize: '13px' }}>
                          <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>SIZE</span>
                          <strong style={{ color: '#fff' }}>{selectedDirectoryCustomer.style_dna?.size || 'S (consistent)'}</strong>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '10px', fontSize: '13px' }}>
                          <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>VISIT PATTERN</span>
                          <strong style={{ color: '#fff' }}>{selectedDirectoryCustomer.style_dna?.visit_pattern || 'Every 15-30 days'}</strong>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '10px', fontSize: '13px' }}>
                          <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>RISK STATUS</span>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700 }}>
                            <span style={{
                              width: '8px',
                              height: '8px',
                              borderRadius: '50%',
                              backgroundColor: selectedDirectoryCustomer.style_dna?.risk_level === 'danger' ? '#ff7675' : '#55efc4',
                              display: 'inline-block'
                            }} />
                            <span style={{ color: selectedDirectoryCustomer.style_dna?.risk_level === 'danger' ? '#ff7675' : '#55efc4' }}>
                              {selectedDirectoryCustomer.style_dna?.risk_status || 'Active — Last visit 0 days ago'}
                            </span>
                          </span>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '10px', fontSize: '13px' }}>
                          <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>NEXT ACTION</span>
                          <strong style={{ color: '#fff' }}>"{selectedDirectoryCustomer.style_dna?.next_action || 'Share seasonal lookbook'}"</strong>
                        </div>

                        {/* Footer Disclaimer */}
                        <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', fontStyle: 'italic', marginTop: '4px', textAlign: 'left' }}>
                          This is NOT manual entry. AI reads your sales data automatically.
                        </div>
                      </div>
                    </div>
                    
                    {/* Saved Designs Gallery */}
                    <div style={{
                      background: 'var(--surface-color)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '12px',
                      padding: '24px'
                    }}>
                      <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '10px', color: 'var(--text-primary)' }}>
                        Saved Designs & Inspiration
                      </h3>
                      {!selectedDirectoryCustomer.design_preferences || selectedDirectoryCustomer.design_preferences.length === 0 ? (
                        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>No saved designs or reference images.</p>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                          {selectedDirectoryCustomer.design_preferences.map((pref, i) => (
                            <div key={pref.id || i} style={{
                              border: pref.is_approved ? '1px solid rgba(16,185,129,0.5)' : '1px solid var(--border-color)',
                              borderRadius: '8px',
                              padding: '14px'
                            }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '10px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                  <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
                                    {pref.source_display || 'Boutique catalogue'}
                                  </span>
                                  {pref.is_approved && (
                                    <span style={{ fontSize: '10px', fontWeight: 700, padding: '2px 8px', borderRadius: '4px', background: 'rgba(16,185,129,0.15)', color: '#10b981' }}>
                                      APPROVED FOR PRODUCTION
                                    </span>
                                  )}
                                </div>
                                {!pref.is_approved && pref.id && (
                                  <button
                                    type="button"
                                    className="btn-secondary"
                                    style={{ fontSize: '12px', padding: '5px 12px' }}
                                    disabled={approvingDesignId === pref.id}
                                    onClick={() => handleApproveDesign(pref.id, pref.reference_images?.[0])}
                                  >
                                    {approvingDesignId === pref.id ? 'Approving…' : 'Approve for production'}
                                  </button>
                                )}
                              </div>

                              {pref.notes && (
                                <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '0 0 10px 0' }}>{pref.notes}</p>
                              )}

                              {pref.reference_images?.length > 0 && (
                                <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                                  {pref.reference_images.map((url, j) => (
                                    <div key={`${i}-${j}`} style={{
                                      borderRadius: '6px',
                                      overflow: 'hidden',
                                      height: '120px',
                                      border: pref.approved_image === url ? '2px solid #10b981' : '1px solid rgba(255,255,255,0.08)'
                                    }}>
                                      <img src={url} alt="Design Ref" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                    </div>
                                  ))}
                                </div>
                              )}

                              {pref.reference_links?.length > 0 && (
                                <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                  {pref.reference_links.map((link, j) => (
                                    <a key={j} href={link} target="_blank" rel="noreferrer"
                                       style={{ fontSize: '11px', color: 'var(--accent-text, #b07c40)', wordBreak: 'break-all' }}>
                                      {link}
                                    </a>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                  </div>

                </div>
              </div>
            )}
            
            {/* 6. INVOICES TAB */}

            {dashboardTab === 'invoices' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        {t('invoicesPage.title', 'Invoices & Billing')}
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{t('invoicesPage.subtitle', 'Manage invoices, verify billing payments, and print receipts.')}</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  </div>
                </header>

                {/* Finance Overview widgets */}
                {(() => {
                  // Collected is what has actually been received, and
                  // outstanding is the same (total - paid) expression the
                  // Balance Due cell in every row below uses. These two used to
                  // count the FULL total_amount of each order -- collected
                  // counted a part-paid order at zero, outstanding counted it
                  // in full -- so the header disagreed with its own table in
                  // both directions on the same screen.
                  const paidTotal = ordersList.reduce((sum, o) => sum + parseFloat(o.amount_paid || 0), 0);
                  const pendingTotal = ordersList.reduce((sum, o) => sum + Math.max(0, parseFloat(o.total_amount || 0) - parseFloat(o.amount_paid || 0)), 0);
                  const grandTotal = ordersList.reduce((sum, o) => sum + parseFloat(o.total_amount), 0);
                  
                  return (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '20px', marginTop: '24px' }}>
                      <div className="stat-card" style={{ padding: '20px', border: '1px solid var(--border-color)' }}>
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>{t('invoicesPage.totalCollectedRevenue', 'Total Collected Revenue')}</span>
                        <div style={{ fontSize: '24px', fontWeight: 700, color: '#107c41', marginTop: '8px' }}>{formatMoney(paidTotal)}</div>
                      </div>
                      <div className="stat-card" style={{ padding: '20px', border: '1px solid var(--border-color)' }}>
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>{t('invoicesPage.outstandingBalance', 'Outstanding Balance')}</span>
                        <div style={{ fontSize: '24px', fontWeight: 700, color: '#d4af37', marginTop: '8px' }}>{formatMoney(pendingTotal)}</div>
                      </div>
                      <div className="stat-card" style={{ padding: '20px', border: '1px solid var(--border-color)' }}>
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>{t('invoicesPage.totalInvoicedVolume', 'Total Invoiced Volume')}</span>
                        <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '8px' }}>{formatMoney(grandTotal)}</div>
                      </div>
                    </div>
                  );
                })()}

                {/* Filters & Search */}
                <div style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: '16px',
                  background: 'var(--surface-color)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '12px',
                  padding: '16px',
                  marginTop: '24px'
                }}>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    {['All', 'Paid', 'Pending'].map(option => (
                      <button 
                        key={option}
                        onClick={() => setInvoiceFilter(option)}
                        className={invoiceFilter === option ? 'btn-primary' : 'btn-secondary'}
                        style={{ padding: '6px 16px', fontSize: '13px' }}
                      >
                        {option === 'All' ? t('common.all', 'All') : option === 'Paid' ? t('invoicesPage.paid', 'Paid') : t('invoicesPage.pending', 'Pending')}
                      </button>
                    ))}
                  </div>

                  <div className="search-bar-container" style={{ width: '100%', maxWidth: '300px', margin: 0 }}>
                    <Search className="search-icon" size={16} />
                    <input 
                      type="text" 
                      placeholder={t('invoicesPage.searchPlaceholder', 'Search Invoice ID or Client...')}
                      className="search-input"
                      value={invoiceSearch}
                      onChange={(e) => setInvoiceSearch(e.target.value)}
                    />
                  </div>
                </div>

                {paymentError && (
                  <div role="alert" style={{ marginTop: '16px', background: '#fdf2f2', border: '1px solid #f5c6c6', color: '#8a2020', borderRadius: '8px', padding: '12px 14px', fontSize: '13px', display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                    <span>{paymentError}</span>
                    <button type="button" onClick={() => setPaymentError(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontWeight: 700 }}>Dismiss</button>
                  </div>
                )}

                <div className="invoices-content" style={{ marginTop: '24px' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', background: 'var(--surface-color)', borderRadius: '12px', border: '1px solid var(--border-color)', overflow: 'hidden' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border-color)', background: 'rgba(0,0,0,0.015)' }}>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>{t('invoicesPage.invoiceId', 'Invoice ID')}</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>{t('invoicesPage.billingClient', 'Billing Client')}</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>{t('common.date', 'Date')}</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>{t('invoicesPage.totalPrice', 'Total Price')}</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>{t('invoicesPage.advancePaid', 'Advance Paid')}</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>{t('invoicesPage.totalPaid', 'Total Paid')}</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>{t('invoicesPage.balanceDue', 'Balance Due')}</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>{t('common.status', 'Payment Status')}</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>{t('common.actions', 'Action')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        const filtered = ordersList.filter(order => {
                          if (invoiceFilter === 'Paid' && order.payment_status !== 'Paid') return false;
                          if (invoiceFilter === 'Pending' && order.payment_status === 'Paid') return false;

                          if (invoiceSearch.trim()) {
                            const query = invoiceSearch.toLowerCase();
                            const matchesId = order.order_id.toLowerCase().includes(query);
                            const matchesClient = (order.customer_name || '').toLowerCase().includes(query);
                            return matchesId || matchesClient;
                          }
                          return true;
                        });

                        if (filtered.length === 0) {
                          return (
                            <tr>
                              <td colSpan="11" style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                                {ordersList.length === 0
                                  ? t('invoicesPage.emptyState', 'Invoices appear here once you have created an order.')
                                  : t('invoicesPage.noMatchingInvoices', 'No invoices matching the criteria.')}
                              </td>
                            </tr>
                          );
                        }

                        return filtered.map(order => (
                          <tr key={order.id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '14px' }}>
                            <td style={{ padding: '16px', fontFamily: 'monospace', fontWeight: 600 }}>{order.order_id}</td>
                            <td style={{ padding: '16px' }}>{order.customer_name}</td>
                            <td style={{ padding: '16px', color: 'var(--text-secondary)' }}>{fmtDate(order.order_date)}</td>
                            <td style={{ padding: '16px', fontWeight: 600 }}>{formatMoney(order.total_amount)}</td>
                            <td style={{ padding: '16px', color: 'var(--text-secondary)' }}>{formatMoney(order.advance_paid)}</td>
                            {/* Editable, because until now there was no screen
                                anywhere that could record a part payment. The
                                only control was the status dropdown beside it,
                                and picking "Partially Paid" sent no amount, so
                                _reconcile_payment re-derived the label from the
                                unchanged number and it snapped straight back to
                                Pending. A customer paying an instalment at the
                                counter could not be recorded at all: only zero
                                and paid-in-full were expressible, which made
                                the ledger, the tracking page's balance and the
                                Analytics totals wrong for every part-paid
                                order. The backend already accepted amount_paid
                                and derives the label, clamps to the total and
                                caps the advance -- only the input was missing. */}
                            <td style={{ padding: '16px', color: '#107c41', fontWeight: 600 }}>
                              <span style={{ marginRight: '2px' }}>₹</span>
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                max={order.total_amount}
                                defaultValue={parseFloat(order.amount_paid || 0)}
                                disabled={savingPaymentId === order.id}
                                aria-label={`Amount paid for invoice ${order.order_id}`}
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
                                    setPaymentError(`Could not record that payment for ${order.order_id} — ${err.message}`);
                                  } finally {
                                    setSavingPaymentId(null);
                                  }
                                }}
                                onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur(); }}
                                style={{ width: '110px', padding: '4px 6px', fontSize: '13px', fontWeight: 600, color: '#107c41', border: '1px solid var(--border-color)', borderRadius: '4px', background: 'transparent' }}
                              />
                            </td>
                            <td style={{ padding: '16px', color: '#ff4d4d', fontWeight: 600 }}>{formatMoney(Math.max(0, Number(order.total_amount) - Number(order.amount_paid || 0)))}</td>
                            <td style={{ padding: '16px' }}>
                              <select 
                                value={order.payment_status}
                                onChange={async (e) => {
                                  try {
                                    await api.updateOrder(order.id, { payment_status: e.target.value });
                                    fetchDashboardAndConfig();
                                  } catch (err) {
                                    e.target.value = order.payment_status;
                                    setPaymentError(`Could not update ${order.order_id} — ${err.message}`);
                                  }
                                }}
                                className="form-control"
                                style={{ padding: '4px 8px', fontSize: '12px', width: '130px', margin: 0 }}
                              >
                                {/* "Partially Paid" is not offered here on
                                    purpose: it is a *derived* label, not a
                                    thing to choose. Selecting it sent no
                                    amount, so the server recomputed the same
                                    label from the same number and the control
                                    snapped back -- a dropdown that visibly
                                    refused its own option. It still appears as
                                    the current value when the amount beside it
                                    puts the order there. Pending and Paid stay
                                    because both are unambiguous shortcuts:
                                    nothing received, and settled in full. */}
                                <option value="Pending">{t('invoicesPage.pending', 'Pending')}</option>
                                {order.payment_status === 'Partially Paid' && (
                                  <option value="Partially Paid">{t('invoicesPage.partiallyPaid', 'Partially Paid')}</option>
                                )}
                                <option value="Paid">{t('invoicesPage.paid', 'Paid')}</option>
                              </select>
                            </td>
                            <td style={{ padding: '16px' }}>
                              <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => {
                                setConfirmedOrder(order);
                                setShowInvoiceModal(true);
                              }}>
                                <FileText size={12} /> {t('invoicesPage.viewInvoice', 'View Invoice')}
                              </button>
                            </td>
                          </tr>
                        ));
                      })()}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {/* 7. ANALYTICS TAB */}
            {dashboardTab === 'analytics' && (() => {
              // Same definition as the Invoices header and the Balance Due
              // cells: collected is money received, not the face value of
              // orders that happen to be labelled Paid. Counting a part-paid
              // order as zero collected and its full value as outstanding was
              // wrong in both directions at once.
              const paidRevenue = ordersList.reduce((sum, o) => sum + parseFloat(o.amount_paid || 0), 0);
              const totalBilling = ordersList.reduce((sum, o) => sum + parseFloat(o.total_amount || 0), 0);
              const pendingBill = Math.max(0, totalBilling - paidRevenue);
              const aov = ordersList.length > 0 ? (totalBilling / ordersList.length) : 0;

              // Counted per garment ordered, not per customer.
              //
              // These three panels read Customer.garment_type, neckline_style and
              // sleeve_style -- one value per person, set by whichever dress was
              // entered last. So a customer who ordered a blouse and a lehenga
              // counted once, and the neckline and sleeve panels were permanently
              // empty because the order wizard writes those onto the garment job
              // and never onto the customer. Read the garment jobs, and take the
              // percentage against the number of garments rather than the number
              // of clients.
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

              return (
                <>
                  <header className="portal-header">
                    <div className="portal-header-left">
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                          {t('analyticsPage.title', 'Business Analytics & Trends')}
                        </h1>
                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{t('analyticsPage.subtitle', 'Summary of revenues, style preferences, and operations workload.')}</p>
                      </div>
                    </div>
                    <div className="portal-header-right">
                      <div className="user-profile-widget">
                        <div className="user-avatar-circle">
                          <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                        </div>
                        <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                      </div>
                    </div>
                  </header>

                  <div className="analytics-metrics-grid" style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                    gap: '24px',
                    marginTop: '24px'
                  }}>
                    {/* Revenue Card */}
                    <div className="metric-panel-card" style={{
                      background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                      border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                      borderRadius: '12px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px'
                    }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>{t('analyticsPage.collectedRevenue', 'Collected Revenue')}</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: 'var(--accent-text, #b07c40)' }}>
                        ₹{paidRevenue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{t('analyticsPage.fromPaidOrders', 'From paid customer orders')}</span>
                    </div>

                    {/* Pending Bills Card */}
                    <div className="metric-panel-card" style={{
                      background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                      border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                      borderRadius: '12px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px'
                    }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>{t('analyticsPage.pendingInvoices', 'Pending Invoices')}</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: '#ffc107' }}>
                        ₹{pendingBill.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{t('analyticsPage.awaitingPayment', 'Awaiting full or partial payment')}</span>
                    </div>

                    {/* Average Order Value Card */}
                    <div className="metric-panel-card" style={{
                      background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                      border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                      borderRadius: '12px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px'
                    }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>{t('analyticsPage.avgTicketSize', 'Average Ticket Size')}</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: '#4a90e2' }}>
                        ₹{aov.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{t('analyticsPage.perBespokeOrder', 'Per bespoke order')}</span>
                    </div>

                    {/* Total Registered Clients */}
                    <div className="metric-panel-card" style={{
                      background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                      border: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
                      borderRadius: '12px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px'
                    }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>{t('analyticsPage.clientBase', 'Client Base')}</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: '#2ec4b6' }}>
                        {customersList.length} {customersList.length === 1 ? t('analyticsPage.clientSingle', 'Client') : t('analyticsPage.clientPlural', 'Clients')}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{t('analyticsPage.totalDirectoryProfiles', 'Total boutique directory profiles')}</span>
                    </div>
                  </div>

                  {/* Operational and Trend Columns */}
                  <div className="analytics-two-col" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px', marginTop: '32px' }}>
                    
                    {/* Left side: Styles & Design Trends */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                      <div className="analytics-card-section" style={{
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.05)',
                        borderRadius: '12px',
                        padding: '24px'
                      }}>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{t('analyticsPage.popularGarmentTypes', 'Popular Garment Types')}</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          {topGarmentsList.map(([garment, count], idx) => {
                            const pct = Math.round((count / garmentTotal) * 100) || 0;
                            return (
                              <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                                  <span>{garment}</span>
                                  <span style={{ fontWeight: 600 }}>{count} ({pct}%)</span>
                                </div>
                                <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                                  <div style={{ width: `${pct}%`, height: '100%', background: 'var(--accent-text, #b07c40)', borderRadius: '3px' }}></div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      <div className="analytics-card-section" style={{
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.05)',
                        borderRadius: '12px',
                        padding: '24px'
                      }}>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{t('analyticsPage.customerSegmentation', 'Customer Segmentation')}</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                          {(() => {
                            const vipCount = customersList.filter(c => c.segment === 'VIP').length;
                            const hvcCount = customersList.filter(c => c.segment === 'HVC').length;
                            const generalCount = customersList.filter(c => c.segment === 'General').length;
                            const total = customersList.length || 1;

                            return [
                              { name: t('analyticsPage.vipCustomer', 'VIP (Very Important Customer)'), count: vipCount, color: '#d4af37' },
                              { name: t('analyticsPage.hvcCustomer', 'HVC (High Value Customer)'), count: hvcCount, color: '#a855f7' },
                              { name: t('analyticsPage.generalCustomers', 'General Customers'), count: generalCount, color: '#9ca3af' }
                            ].map((seg, idx) => {
                              const pct = Math.round((seg.count / total) * 100);
                              return (
                                <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                      <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: seg.color }}></span>
                                      {seg.name}
                                    </span>
                                    <span style={{ fontWeight: 600 }}>{seg.count} ({pct}%)</span>
                                  </div>
                                  <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                                    <div style={{ width: `${pct}%`, height: '100%', background: seg.color, borderRadius: '3px' }}></div>
                                  </div>
                                </div>
                              );
                            });
                          })()}
                        </div>
                      </div>

                      <div className="analytics-card-section" style={{
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.05)',
                        borderRadius: '12px',
                        padding: '24px'
                      }}>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{t('analyticsPage.necklineSleeveTrends', 'Neckline & Sleeve Trends')}</h3>
                        <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                          <div>
                            <h4 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase' }}>{t('analyticsPage.topNecklines', 'Top Necklines')}</h4>
                            {topNecklinesList.map(([style, count], idx) => (
                              <div key={idx} style={{ fontSize: '13px', display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                                <span>{style}</span>
                                <span style={{ fontWeight: 600 }}>{count}</span>
                              </div>
                            ))}
                          </div>
                          <div>
                            <h4 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase' }}>{t('analyticsPage.topSleeves', 'Top Sleeves')}</h4>
                            {topSleevesList.map(([style, count], idx) => (
                              <div key={idx} style={{ fontSize: '13px', display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                                <span>{style}</span>
                                <span style={{ fontWeight: 600 }}>{count}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Right side: Staff & Internal Metrics */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                      <div className="analytics-card-section" style={{
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.05)',
                        borderRadius: '12px',
                        padding: '24px'
                      }}>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{t('analyticsPage.staffWorkloadOverview', 'Staff & Workload Overview')}</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', fontSize: '14px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span>{t('analyticsPage.totalTailoringTeam', 'Total Tailoring Team')}</span>
                            <span style={{ fontWeight: 600 }}>{tailors.length} {tailors.length === 1 ? t('analyticsPage.tailorSingle', 'Tailor') : t('analyticsPage.tailorPlural', 'Tailors')}</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span>{t('analyticsPage.busyAssignedTailors', 'Busy / Assigned Tailors')}</span>
                            <span style={{ fontWeight: 600, color: '#ffc107' }}>{busyTailors} {t('analyticsPage.busyStatus', 'Busy')}</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span>{t('analyticsPage.availableStaffCapacity', 'Available Staff capacity')}</span>
                            <span style={{ fontWeight: 600, color: '#2ec4b6' }}>{tailors.length - busyTailors} {t('analyticsPage.freeStatus', 'Free')}</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span>{t('analyticsPage.atelierAvgRating', 'Atelier Average Rating')}</span>
                            <span style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                              ⭐ {avgTailorRating.toFixed(2)}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="analytics-card-section" style={{
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.05)',
                        borderRadius: '12px',
                        padding: '24px'
                      }}>
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{t('analyticsPage.orderStatusBreakdown', 'Order Status Breakdown')}</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          {Object.entries(dashboardData?.stats?.status_distribution || {}).map(([status, count], idx) => {
                            const pct = Math.round((count / ordersList.length) * 100) || 0;
                            return (
                              <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                <div style={{ display: 'flex', justifycontent: 'space-between', fontSize: '13px' }}>
                                  <span>{t(`status.${status}`, status)}</span>
                                  <span style={{ fontWeight: 600 }}>{count} ({pct}%)</span>
                                </div>
                                <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                                  <div style={{ width: `${pct}%`, height: '100%', background: '#4a90e2', borderRadius: '3px' }}></div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>

                  </div>
                </>
              );
            })()}

            {/* 8. MY ACCOUNT SETTINGS TAB */}
            {dashboardTab === 'account' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        {t('accountPage.title')}
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{t('accountPage.subtitle')}</p>
                    </div>
                  </div>
                  <div className="portal-header-right" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>{t('dashboard.hiUser', `Hi, ${currentUserName}`, { name: currentUserName })}</span>
                    </div>
                  </div>
                </header>


                <div className="account-settings-container" style={{ marginTop: '24px', display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '32px' }}>
                  {/* Left profile summary */}
                  <div className="content-card" style={{ alignItems: 'center', textAlign: 'center', gap: '16px' }}>
                    <div className="profile-large-avatar" style={{
                      width: '120px',
                      height: '120px',
                      borderRadius: '50%',
                      overflow: 'hidden',
                      border: '3px solid var(--accent-text, #b07c40)'
                    }}>
                      <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=200" alt="Profile" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    </div>
                    <div>
                      <h3 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>{currentUser.first_name} {currentUser.last_name}</h3>
                      {/* The signed-in role, not a hardcoded claim. This said
                          "Boutique Owner" to every account -- tailors, masters
                          and designers included -- on the one screen whose job
                          is telling you who you are signed in as. */}
                      <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>{currentUser.role || 'Boutique Owner'}</p>
                    </div>
                    
                    <div style={{ width: '100%', height: '1px', background: 'var(--border-color, rgba(255,255,255,0.08))' }}></div>
                    
                    <div style={{ alignSelf: 'stretch', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
                      <div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: '11px', textTransform: 'uppercase' }}>{t('accountPage.tenantDomain', 'Tenant Domain')}</div>
                        <div style={{ fontWeight: 600, color: 'var(--accent-text, #b07c40)' }}>
                          {localStorage.getItem('tenant_id') || '--'}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: '11px', textTransform: 'uppercase' }}>{t('accountPage.atelierEmail', 'Atelier Email')}</div>
                        <div style={{ fontWeight: 600 }}>{currentUser.email}</div>
                      </div>
                      {/* "Registered Since: June 2024" was a literal, shown to
                          every boutique whatever date they actually signed up.
                          Nothing in the API carries the tenant's created_on, so
                          the row is gone rather than invented -- an absent fact
                          beats a confident wrong one. Restore it by adding
                          created_on to the MeView payload. */}
                    </div>
                  </div>

                  {/* Owner only. Every role saw this form, and submitting it
                      POSTs /boutique-settings/ -- whose `create` action is on
                      neither the safe-method list nor the named-action list in
                      RolePermission, so a Master, Tailor or Designer got a
                      certain 403 rendered as "Failed to update boutique
                      settings" with no reason given. A form that cannot
                      succeed should not be drawn. */}
                  {(!currentUser?.role || currentUser.role === 'Owner') && (
                  <div className="content-card">
                    <h3 className="card-title">{t('accountPage.editProfile', 'Edit Boutique Profile')}</h3>
                    <form 
                      style={{ display: 'flex', flexDirection: 'column', gap: '20px' }} 
                      onSubmit={async (e) => {
                        e.preventDefault();
                        const form = e.target;
                        const formData = new FormData();
                        formData.append('name', form.boutiqueName.value);
                        formData.append('address', form.boutiqueAddress.value);
                        formData.append('phone', form.boutiquePhone.value);
                        formData.append('email', form.boutiqueEmail.value);
                        if (form.boutiqueLogo.files[0]) {
                          formData.append('logo', form.boutiqueLogo.files[0]);
                        }
                        formData.append('design_approval_required', form.designApprovalRequired.checked);
                        try {
                          const updated = await api.updateBoutiqueSettings(formData);
                          setBoutiqueSettings(updated);
                          alert("Boutique settings updated successfully!");
                        } catch (err) {
                          console.error(err);
                          alert("Failed to update boutique settings");
                        }
                      }}
                    >
                      <div className="form-group">
                        <label className="form-label">{t('accountPage.boutiqueName', 'Boutique Name')}</label>
                        <input 
                          type="text" 
                          name="boutiqueName"
                          className="form-control" 
                          defaultValue={boutiqueSettings?.name || ''}
                          placeholder="e.g. Aditi's Atelier" 
                          required
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">{t('accountPage.boutiqueAddress', 'Boutique Address')}</label>
                        <textarea 
                          name="boutiqueAddress"
                          className="form-control" 
                          style={{ minHeight: '80px', resize: 'vertical' }}
                          defaultValue={boutiqueSettings?.address || ''}
                          placeholder="Street, area, city, PIN" 
                          required
                        />
                      </div>

                      <div className="form-grid-2">
                        <div className="form-group">
                          <label className="form-label">{t('accountPage.boutiquePhone', 'Boutique Phone')}</label>
                          <input 
                            type="text" 
                            name="boutiquePhone"
                            className="form-control" 
                            defaultValue={boutiqueSettings?.phone || ''}
                            placeholder="+91 98765 43210" 
                            required
                          />
                        </div>
                        <div className="form-group">
                          <label className="form-label">{t('accountPage.boutiqueEmail', 'Boutique Email')}</label>
                          <input 
                            type="email" 
                            name="boutiqueEmail"
                            className="form-control" 
                            defaultValue={boutiqueSettings?.email || ''}
                            placeholder="you@yourboutique.com" 
                            required
                          />
                        </div>
                      </div>

                      <div className="form-group">
                        <label className="form-label">{t('accountPage.boutiqueLogo', 'Boutique Logo')}</label>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginTop: '4px' }}>
                          {boutiqueSettings?.logo && (
                            <img 
                              src={boutiqueSettings.logo} 
                              alt="Boutique Logo" 
                              style={{ width: '48px', height: '48px', borderRadius: '4px', objectFit: 'contain', background: '#f8fafc', border: '1px solid var(--border-color)' }} 
                            />
                          )}
                          <input 
                            type="file" 
                            name="boutiqueLogo"
                            accept="image/*"
                            className="form-control" 
                          />
                        </div>
                      </div>

                      <div className="form-group">
                        {/* Off by default: a small team is usually the owner and
                            one or two designers, and a queue with nobody to clear
                            it is friction with no benefit. */}
                        <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            name="designApprovalRequired"
                            defaultChecked={!!boutiqueSettings?.design_approval_required}
                          />
                          <span>
                            <span style={{ fontWeight: 600 }}>{t('accountPage.requireApproval', 'Require approval for new designs')}</span>
                            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                              {t('accountPage.approvalHelp', 'When on, uploads from staff other than you wait for your review before appearing in the library.')}
                            </div>
                          </span>
                        </label>
                      </div>

                      <button type="submit" className="btn-primary" style={{ alignSelf: 'flex-start', marginTop: '8px' }}>
                        {t('accountPage.saveChanges', 'Save Changes')}
                      </button>
                    </form>
                  </div>
                  )}
                </div>
              </>
            )}

            {/* 9. SETTINGS TAB */}
            {dashboardTab === 'settings' && (
              <SettingsPage currentUser={currentUser} boutiqueSettings={boutiqueSettings} />
            )}
          </main>

          {/* Fabrics CRUD Modal Overlay */}
          {showFabricModal && (
            <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100 }}>
              <div className="search-modal-card" style={{ maxWidth: '500px', width: '100%' }}>
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)' }}>
                    {editingFabric ? t('fabricsPage.editFabricDetails', 'Edit Fabric Details') : t('fabricsPage.addNewFabricTitle', 'Add New Fabric to Catalog')}
                  </h3>
                  <button className="close-btn" onClick={() => setShowFabricModal(false)}><X size={20} /></button>
                </div>
                
                <form onSubmit={handleSaveFabric} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('fabricsPage.fabricName', 'Fabric Name')}</label>
                    <input 
                      type="text" 
                      required 
                      className="form-control" 
                      placeholder="e.g. Chanderi Silk" 
                      value={fabricForm.name}
                      onChange={e => setFabricForm({...fabricForm, name: e.target.value})}
                    />
                  </div>

                  <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('fabricsPage.material', 'Material')}</label>
                      <input 
                        type="text" 
                        required 
                        className="form-control" 
                        placeholder="e.g. Silk Blend" 
                        value={fabricForm.material}
                        onChange={e => setFabricForm({...fabricForm, material: e.target.value})}
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('fabricsPage.color', 'Color')}</label>
                      <input 
                        type="text" 
                        required 
                        className="form-control" 
                        placeholder="e.g. Aqua Blue" 
                        value={fabricForm.color}
                        onChange={e => setFabricForm({...fabricForm, color: e.target.value})}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('fabricsPage.pricePerMeterLabel', 'Price per Meter (₹)')}</label>
                    <input 
                      type="number" 
                      required 
                      min="0"
                      step="0.01"
                      className="form-control" 
                      placeholder="e.g. 1250" 
                      value={fabricForm.price_per_meter}
                      onChange={e => setFabricForm({...fabricForm, price_per_meter: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('fabricsPage.imageUrlOptional', 'Image URL (Optional)')}</label>
                    <input 
                      type="url" 
                      className="form-control" 
                      placeholder="e.g. https://images.unsplash.com/photo-..." 
                      value={fabricForm.image_url}
                      onChange={e => setFabricForm({...fabricForm, image_url: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '4px 0' }}>
                    <input 
                      type="checkbox" 
                      id="fabricAvailable"
                      checked={fabricForm.is_available}
                      onChange={e => setFabricForm({...fabricForm, is_available: e.target.checked})}
                    />
                    <label htmlFor="fabricAvailable" style={{ fontSize: '13px', cursor: 'pointer' }}>{t('fabricsPage.availableInInventory', 'Available in Inventory')}</label>
                  </div>

                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px', marginTop: '8px' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShowFabricModal(false)}>{t('common.cancel', 'Cancel')}</button>
                    <button type="submit" className="btn-primary">{t('fabricsPage.saveFabric', 'Save Fabric')}</button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Appointment booking. apps/scheduling has always accepted these and
              the customer's tracking page already renders a trial card from
              them; there was simply no way to create one from the product. */}
          {showAppointmentModal && (
            <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100 }}>
              <div className="search-modal-card" style={{ maxWidth: '460px', width: '100%' }}>
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)' }}>
                    Book an Appointment
                  </h3>
                  <button className="close-btn" onClick={() => setShowAppointmentModal(false)}><X size={20} /></button>
                </div>
                <form onSubmit={handleSaveAppointment} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div>
                    <label className="form-label">Client *</label>
                    <select className="form-control" required
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
                  <div>
                    <label className="form-label">Notes</label>
                    <textarea className="form-control" rows={2}
                              value={appointmentForm.notes}
                              onChange={(e) => setAppointmentForm({ ...appointmentForm, notes: e.target.value })} />
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', justifyContent: 'flex-end' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShowAppointmentModal(false)}>Cancel</button>
                    <button type="submit" className="btn-primary" disabled={savingAppointment}>
                      {savingAppointment ? 'Booking…' : 'Book appointment'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Tailors CRUD Modal Overlay */}
          {showTailorModal && (
            <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100 }}>
              <div className="search-modal-card" style={{ maxWidth: '500px', width: '100%' }}>
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)' }}>
                    {editingTailor ? t('tailorsPage.editTailorTitle', 'Edit Tailor Details') : t('tailorsPage.addTailorTitle', 'Add New Tailor Profile')}
                  </h3>
                  <button className="close-btn" onClick={() => setShowTailorModal(false)}><X size={20} /></button>
                </div>
                
                <form onSubmit={handleSaveTailor} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('tailorsPage.tailorName', 'Tailor Name')}</label>
                    <input 
                      type="text" 
                      required 
                      className="form-control" 
                      placeholder="e.g. Master Shabbir" 
                      value={tailorForm.name}
                      onChange={e => setTailorForm({...tailorForm, name: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('tailorsPage.emailAddressLogin', 'Email Address (for login)')}</label>
                    <input 
                      type="email" 
                      required 
                      className="form-control" 
                      placeholder="e.g. shabbir@boutique.com" 
                      value={tailorForm.email || ''}
                      onChange={e => setTailorForm({...tailorForm, email: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('tailorsPage.specialty', 'Specialty')}</label>
                    <input 
                      type="text" 
                      required 
                      className="form-control" 
                      placeholder="e.g. Lehenga Specialist, Gowns" 
                      value={tailorForm.specialty}
                      onChange={e => setTailorForm({...tailorForm, specialty: e.target.value})}
                    />
                  </div>

                  <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('tailorsPage.ratingLabel', 'Rating (1.0 — 5.0)')}</label>
                      <input 
                        type="number" 
                        required 
                        min="1"
                        max="5"
                        step="0.1"
                        className="form-control" 
                        placeholder="5.0" 
                        value={tailorForm.rating}
                        onChange={e => setTailorForm({...tailorForm, rating: e.target.value})}
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('common.status', 'Status')}</label>
                      <select 
                        className="form-control"
                        value={tailorForm.status}
                        onChange={e => setTailorForm({...tailorForm, status: e.target.value})}
                      >
                        <option value="Available">{t('tailorsPage.available', 'Available')}</option>
                        <option value="Busy">{t('tailorsPage.busy', 'Busy')}</option>
                      </select>
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('tailorsPage.staffRole', 'Staff Role')}</label>
                    <select 
                      className="form-control"
                      value={tailorForm.role}
                      onChange={e => setTailorForm({...tailorForm, role: e.target.value})}
                    >
                      {STAFF_ROLES.map(r => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {STAFF_ROLES.find(r => r.value === tailorForm.role)?.hint || ''}
                    </span>
                  </div>

                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px', marginTop: '8px' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShowTailorModal(false)}>{t('common.cancel', 'Cancel')}</button>
                    <button type="submit" className="btn-primary">{t('tailorsPage.saveTailorBtn', 'Save Tailor')}</button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Share Tailor Credentials Modal Overlay */}
          {shareCredsTailor && (
            <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100 }}>
              <div className="search-modal-card" style={{ maxWidth: '500px', width: '100%' }}>
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)' }}>
                    {t('tailorsPage.shareCredentialsTitle', 'Share Login Credentials')}
                  </h3>
                  <button className="close-btn" onClick={() => setShareCredsTailor(null)}><X size={20} /></button>
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                  <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                    {t('tailorsPage.shareCredentialsHelp', 'Provide these credentials so they can log in to view and manage their assignments.')}
                  </p>

                  <div style={{ background: 'rgba(0,0,0,0.02)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>{t('tailorsPage.loginPortalUrl', 'Login Portal URL')}</span>
                      <div style={{ fontWeight: 600, fontSize: '14px', marginTop: '2px', wordBreak: 'break-all' }}>{window.location.origin}</div>
                    </div>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>{t('tailorsPage.usernameEmail', 'Username / Email')}</span>
                      <div style={{ fontWeight: 600, fontSize: '14px', marginTop: '2px', wordBreak: 'break-all' }}>{shareCredsTailor.email}</div>
                    </div>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>{t('tailorsPage.temporaryPassword', 'Temporary Password')}</span>
                      {shareCredsTailor.bootstrap_password ? (
                        <div style={{ fontWeight: 600, fontSize: '14px', marginTop: '2px', fontFamily: 'ui-monospace, monospace', letterSpacing: '.5px' }}>{shareCredsTailor.bootstrap_password}</div>
                      ) : (
                        <div style={{ fontSize: '13px', marginTop: '2px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                          Shown only once, when the account was created. Ask {shareCredsTailor.name} to use
                          <strong> Forgot password?</strong> on the sign-in screen to set a new one.
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px', marginTop: '8px' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShareCredsTailor(null)}>{t('common.cancel', 'Close')}</button>
                    
                    {/* Copy to Clipboard */}
                    <button 
                      type="button" 
                      className="btn-secondary" 
                      onClick={() => {
                        const txt = shareCredsTailor.bootstrap_password
                          ? `Atelier Staff Login Credentials:\nPortal: ${window.location.origin}\nEmail: ${shareCredsTailor.email}\nPassword: ${shareCredsTailor.bootstrap_password}`
                          : `Atelier Staff Login:\nPortal: ${window.location.origin}\nEmail: ${shareCredsTailor.email}\nUse "Forgot password?" on the sign-in screen to set your password.`;
                        navigator.clipboard.writeText(txt);
                        alert("Credentials copied to clipboard!");
                      }}
                      style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                      <Copy size={14} /> {t('tailorsPage.copyBtn', 'Copy')}
                    </button>

                    {/* Share via WhatsApp */}
                    <button 
                      type="button" 
                      className="btn-primary" 
                      onClick={() => {
                        const msg = encodeURIComponent(shareCredsTailor.bootstrap_password
                          ? `Hello ${shareCredsTailor.name},\nHere are your Atelier login credentials:\nPortal: ${window.location.origin}\nEmail: ${shareCredsTailor.email}\nPassword: ${shareCredsTailor.bootstrap_password}\n\nPlease log in to view your supervised/stitch tasks.`
                          : `Hello ${shareCredsTailor.name},\nYour Atelier login is ready:\nPortal: ${window.location.origin}\nEmail: ${shareCredsTailor.email}\n\nUse "Forgot password?" on the sign-in screen to set your password, then log in to view your tasks.`);
                        window.open(`https://wa.me/?text=${msg}`);
                      }}
                      style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                      <MessageSquare size={14} /> {t('tailorsPage.shareWhatsappBtn', 'Share WhatsApp')}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Designs CRUD Modal Overlay */}
          {showDesignModal && (
            <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100 }}>
              <div className="search-modal-card" style={{ maxWidth: '500px', width: '100%' }}>
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)' }}>
                    {editingDesign ? t('designsPage.editDesignDetails', 'Edit Design Details') : t('designsPage.addNewDesignTitle', 'Add New Design to Collection')}
                  </h3>
                  <button className="close-btn" onClick={() => setShowDesignModal(false)}><X size={20} /></button>
                </div>
                
                <form onSubmit={handleSaveDesign} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('designsPage.designName', 'Design Name')}</label>
                    <input 
                      type="text" 
                      required 
                      className="form-control" 
                      placeholder="e.g. Royal Maroon Velvet Lehenga" 
                      value={designForm.name}
                      onChange={e => setDesignForm({...designForm, name: e.target.value})}
                    />
                  </div>

                  <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('designsPage.garmentCategory', 'Garment Category')}</label>
                      <select 
                        className="form-control"
                        value={designForm.garment_type}
                        onChange={e => setDesignForm({...designForm, garment_type: e.target.value})}
                      >
                        <option value="Lehenga">{t('designsPage.lehenga', 'Lehenga')}</option>
                        <option value="Gown">{t('designsPage.gown', 'Gown')}</option>
                        <option value="Saree">{t('designsPage.saree', 'Saree')}</option>
                        <option value="Kurti">{t('designsPage.kurti', 'Kurti')}</option>
                        <option value="Sherwani">{t('designsPage.sherwani', 'Sherwani')}</option>
                        <option value="Anarkali">{t('designsPage.anarkali', 'Anarkali')}</option>
                      </select>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('designsPage.designType', 'Design Type')}</label>
                      <select 
                        className="form-control"
                        value={designForm.is_boutique}
                        onChange={e => setDesignForm({...designForm, is_boutique: e.target.value === 'true' || e.target.value === true})}
                      >
                        <option value="true">{t('designsPage.boutiqueCatalogCollection', 'Boutique Catalog Collection')}</option>
                        <option value="false">{t('designsPage.aiSuggestionTemplate', 'AI Suggestion Template')}</option>
                      </select>
                    </div>
                  </div>

                  <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('designsPage.necklineStyleOptional', 'Neckline Style (Optional)')}</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="e.g. Sweetheart Neck" 
                        value={designForm.neckline_style}
                        onChange={e => setDesignForm({...designForm, neckline_style: e.target.value})}
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('designsPage.sleeveStyleOptional', 'Sleeve Style (Optional)')}</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="e.g. Cap Sleeve" 
                        value={designForm.sleeve_style}
                        onChange={e => setDesignForm({...designForm, sleeve_style: e.target.value})}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('designsPage.catalogPriceLabel', 'Catalog Price (₹) - Only for Boutique Catalog')}</label>
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
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('designsPage.imageUrlOptional', 'Image URL (Optional)')}</label>
                    <input 
                      type="url" 
                      className="form-control" 
                      placeholder="e.g. https://images.unsplash.com/photo-..." 
                      value={designForm.image_url}
                      onChange={e => setDesignForm({...designForm, image_url: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>{t('designsPage.descriptionOptional', 'Description (Optional)')}</label>
                    <textarea 
                      className="form-control" 
                      placeholder="e.g. Hand-embroidered with gold thread, georgette base..." 
                      rows="3"
                      value={designForm.description}
                      onChange={e => setDesignForm({...designForm, description: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px', marginTop: '8px' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShowDesignModal(false)}>{t('common.cancel', 'Cancel')}</button>
                    <button type="submit" className="btn-primary">{t('designsPage.saveDesign', 'Save Design')}</button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Bottom navigation, phones only.
              It belongs to this view, not the order selector it was originally
              written into: its tabs drive dashboardTab, which only the dashboard
              renders, so from anywhere else every tab was inert. */}
          <BottomNavigation
            tabs={
              (!currentUser.role || currentUser.role === 'Owner') ? [
                { key: 'overview', label: 'Dashboard', icon: Users },
                { key: 'orders', label: 'Orders', icon: ShoppingBag },
                { key: 'customers', label: 'Customers', icon: Users },
                { key: 'inventory', label: 'Inventory', icon: Package },
                { key: 'more', label: 'Menu', icon: Menu }
              ] : currentUser.role === 'Master' ? [
                { key: 'assignments', label: 'Assignments', icon: Scissors },
                { key: 'orders', label: 'Orders', icon: ShoppingBag },
                { key: 'customers', label: 'Customers', icon: Users },
                { key: 'more', label: 'Menu', icon: Menu }
              ] : [
                { key: 'assignments', label: 'Assignments', icon: Scissors },
                { key: 'account', label: 'Account', icon: User },
                { key: 'more', label: 'Menu', icon: Menu }
              ]
            }
            activeTab={dashboardTab}
            onChangeTab={(t) => { setDashboardTab(t); setSelectedDirectoryCustomer(null); }}
            onOpenMore={() => setMobileNavOpen(true)}
          />
        </div>
      )}

      {/* 5. ORDER TYPE SELECTOR (Image 5) */}
      {view === 'order-selector' && (
        <div className="portal-layout">
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
              api.markNotificationsAsRead(currentUser?.role || 'Owner', currentUser?.email)
                .then(() => fetchNotifications())
                    // Never let the bell take the app down: a refused or failed
                    // mark-read is not worth losing the session over.
                    .catch(() => {});
            }}
          />

          {mobileNavOpen && (
            <div className="mobile-portal-overlay" onClick={() => setMobileNavOpen(false)} />
          )}

          {/* Reuse Sidebar for Portal Continuity */}
          <aside className={`portal-sidebar ${mobileNavOpen ? 'mobile-open' : ''}`}>
            <div className="portal-sidebar-logo">SCALEEZY</div>
            <div className="portal-sidebar-logo-sub">THE ATELIER EXPERIENCE</div>
            
            <nav className="portal-menu">
              {(!currentUser.role || currentUser.role === 'Owner') ? (
                <>
                  <a className={`portal-menu-item ${dashboardTab === 'overview' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('overview'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Users size={16} /> {t('nav.dashboard')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'orders' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('orders'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><ShoppingBag size={16} /> {t('nav.manageOrders')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'customers' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('customers'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Users size={16} /> {t('nav.customers')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'invoices' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('invoices'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><FileText size={16} /> {t('nav.invoices')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'analytics' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('analytics'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><BarChart2 size={16} /> {t('nav.analytics')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'fabrics' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('fabrics'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Compass size={16} /> {t('nav.manageFabrics')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'inventory' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('inventory'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Package size={16} /> {t('nav.inventory')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'tailors' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('tailors'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Scissors size={16} /> {t('nav.manageTailors')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'designs' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('designs'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Sparkles size={16} /> {t('nav.manageDesigns')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'designWork' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('designWork'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><PenTool size={16} /> {t('nav.designWork')}</a>
                </>
              ) : currentUser.role === 'Master' ? (
                <>
                  <a className={`portal-menu-item ${dashboardTab === 'assignments' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('assignments'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Scissors size={16} /> {t('nav.myAssignments')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'orders' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('orders'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><ShoppingBag size={16} /> {t('nav.manageOrders')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'customers' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('customers'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Users size={16} /> {t('nav.customers')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'designWork' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('designWork'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><PenTool size={16} /> {t('nav.designWork')}</a>
                </>
              ) : currentUser.role === 'Designer' ? (
                <>
                  <a className={`portal-menu-item ${dashboardTab === 'designWork' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('designWork'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><PenTool size={16} /> {t('nav.myWork')}</a>
                  <a className={`portal-menu-item ${dashboardTab === 'designs' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('designs'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Sparkles size={16} /> {t('nav.designStudio')}</a>
                </>
              ) : (
                <a className={`portal-menu-item ${dashboardTab === 'assignments' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('assignments'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Scissors size={16} /> {t('nav.myAssignments')}</a>
              )}
              <a className={`portal-menu-item ${dashboardTab === 'account' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('account'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><User size={16} /> {t('nav.account')}</a>
              <a className={`portal-menu-item ${dashboardTab === 'settings' ? 'active' : ''}`} onClick={() => { setView('dashboard'); setDashboardTab('settings'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Settings size={16} /> {t('nav.settings')}</a>
              <a className="portal-menu-item" onClick={() => { handleLogout(); setMobileNavOpen(false); }}><LogOut size={16} /> {t('nav.logout')}</a>
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
                              <button type="button" className="btn-primary" onClick={async () => {
                                try {
                                  await api.deleteOrderDraft(draft.id);
                                  setResumableDrafts(prev => prev.filter(d => d.id !== draft.id));
                                } catch (err) {
                                  console.error('Could not discard the draft', err);
                                  alert('Could not discard that order — it is still saved.');
                                } finally {
                                  setDiscardingDraftId(null);
                                }
                              }}>
                                {t('entry.discardPermanently', 'Discard permanently')}
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
                {/* Option 1: Existing Customer */}
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

                {/* Option 2: New Customer */}
                <div className="selector-option-card" onClick={handleStartNewCustomer}>
                  <div className="selector-option-icon">
                    <User size={32} />
                  </div>
                  <h3 className="selector-option-title">{t('entry.newCustomerTitle', 'New Customer')}</h3>
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
                    {t('entry.createNewCustomerBtn', 'Create New Customer')}
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
                        {t('wizard.uploadPhoto', 'Upload Photo')}
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
                  <div style={{ background: 'rgba(0,0,0,0.015)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '16px', marginBottom: '20px', textAlign: 'left' }}>
                    <label className="form-label" style={{ fontWeight: 600, display: 'block', marginBottom: '4px' }}>
                      {t('wizard.dressesInOrder', 'Dresses in this Order')} <span className="required">*</span>
                    </label>
                    <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                      {t('wizard.dressesInOrderSub', 'Pick every garment being stitched. Each one gets its own measurements and options.')}
                    </div>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      {garmentTemplates.map(template => {
                        const chosen = garmentJobs.some(job => job.key === template.key);
                        return (
                          <button
                            key={template.key}
                            type="button"
                            className={chosen ? 'btn-primary' : 'btn-secondary'}
                            style={{ padding: '7px 14px', fontSize: '13px', borderRadius: '999px', gap: '6px' }}
                            onClick={() => (chosen ? removeGarment(template.key) : addGarment(template.key))}
                          >
                            {chosen ? <Check size={13} /> : <Plus size={13} />}
                            {template.name}
                          </button>
                        );
                      })}
                    </div>
                    {garmentTemplates.length === 0 && (
                      <div style={{ fontSize: '12.5px', color: garmentTemplatesError ? '#c0392b' : 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span>
                          {garmentTemplatesError
                            ? `The garment list could not be loaded — ${garmentTemplatesError}`
                            : 'Loading the garment list…'}
                        </span>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '4px 10px', fontSize: '12px' }}
                          onClick={loadGarmentTemplates}
                        >
                          {t('common.retry', 'Retry')}
                        </button>
                      </div>
                    )}
                    {garmentTemplates.length > 0 && garmentJobs.length === 0 && (
                      <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginTop: '12px' }}>
                        {t('wizard.noGarmentChosen', 'No garment chosen yet.')}
                      </div>
                    )}
                  </div>

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
                  <h1 className="page-title">AI Design Studio</h1>
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
                      <div style={{ background: 'rgba(0,0,0,0.015)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '14px 16px', marginBottom: '20px', textAlign: 'left' }}>
                        <label className="form-label" style={{ fontWeight: 600, display: 'block', marginBottom: '4px' }}>
                          {t('wizard.dressesInOrder', 'Dresses in this Order')}
                        </label>
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '10px' }}>
                          Select garments to see AI design suggestions for each dress.
                        </div>
                        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                          {garmentTemplates.map(template => {
                            const chosen = garmentJobs.some(job => job.key === template.key);
                            return (
                              <button
                                key={template.key}
                                type="button"
                                className={chosen ? 'btn-primary' : 'btn-secondary'}
                                style={{ padding: '6px 12px', fontSize: '12px', borderRadius: '999px', gap: '6px' }}
                                onClick={() => (chosen ? (garmentJobs.length > 1 && removeGarment(template.key)) : addGarment(template.key))}
                              >
                                {chosen ? <Check size={12} /> : <Plus size={12} />}
                                {template.name}
                              </button>
                            );
                          })}
                        </div>
                      </div>

                      {garmentJobs.length === 0 ? (
                        <p style={{ color: 'var(--text-secondary)', padding: '20px 0' }}>
                          Select a garment above to see AI designs matched to it.
                        </p>
                      ) : garmentJobs.map(job => (
                        <div key={job.key} style={{ marginBottom: '28px' }}>
                          {garmentJobs.length > 1 && (
                            <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '10px' }}>
                              {job.template?.name || job.key}
                            </h3>
                          )}
                          <DesignStudio
                            customerId={customerId}
                            draftId={customerId ? null : draftId}
                            garmentKey={job.key}
                            garmentName={job.template?.name || job.key}
                            initialItems={job.design?.items}
                            orderInput={{
                              garment_type: job.template?.key || job.key,
                              occasion: customerForm.occasion,
                              budget: jobSubtotal(job),
                            }}
                            notes={designNotes}
                            onNotesChange={setDesignNotes}
                            onBoardChange={(state) => handleGarmentBoardChange(job.key, state)}
                          />
                        </div>
                      ))}
                    </Suspense>
                  )}

                  {designSourceTab === 'references' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                      <div className="card-title">
                        <Upload size={18} />
                        Share Your Design References
                      </div>

                      {/* Where the design came from, recorded against the order so the
                          workroom knows whether it is following a catalogue piece or
                          a client's own sketch. */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <label style={{ fontSize: '12px', fontWeight: 600 }}>Where is this design from?</label>
                          <select
                            className="form-control"
                            value={designSource}
                            onChange={e => setDesignSource(e.target.value)}
                          >
                            {DESIGN_SOURCES.map(s => (
                              <option key={s.value} value={s.value}>{s.label}</option>
                            ))}
                          </select>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <label style={{ fontSize: '12px', fontWeight: 600 }}>Inspiration links</label>
                          <input
                            type="text"
                            className="form-control"
                            placeholder="Paste Pinterest or image links, comma separated"
                            value={designLinks}
                            onChange={e => setDesignLinks(e.target.value)}
                          />
                        </div>
                      </div>
                      <div className="drag-drop-zone" onClick={() => document.getElementById('design-picker').click()}>
                        <div className="drag-drop-icon">
                          <Upload size={24} />
                        </div>
                        <div className="drag-drop-text">Drag & drop images here or <span>Upload Images</span></div>
                        <div className="drag-drop-subtext">JPG, PNG up to 10MB each • You can upload up to 10 images</div>
                        <input
                          type="file"
                          id="design-picker"
                          multiple
                          accept="image/*"
                          style={{ display: 'none' }}
                          onChange={handleDesignFilesChange}
                        />
                      </div>

                      {designPreviews.length > 0 && (
                        <div className="uploaded-references-section">
                          <div className="section-subtitle">Your Uploaded References ({designPreviews.length}/10)</div>
                          <div className="references-grid">
                            {designPreviews.map((src, i) => (
                              <div className="reference-image-card" key={i}>
                                <img src={src} alt={`Ref ${i+1}`} />
                                <button className="remove-image-btn" onClick={() => {
                                  setDesignPreviews(prev => prev.filter((_, idx) => idx !== i));
                                  setDesignFiles(prev => prev.filter((_, idx) => idx !== i));
                                }}>×</button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}

            {/* STEP 2: Fabric Selection */}
            {currentStep === 2 && (
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
                  </div>

                  {fabricTab === 'my-fabric' ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                      <div className="drag-drop-zone" onClick={() => document.getElementById('fabric-picker').click()}>
                        <div className="drag-drop-icon">
                          <Upload size={24} />
                        </div>
                        <div className="drag-drop-text">Upload Fabric Images</div>
                        <div className="drag-drop-subtext">Upload clear, well-lit photos for accurate representation</div>
                        <input 
                          type="file" 
                          id="fabric-picker" 
                          multiple 
                          accept="image/*" 
                          style={{ display: 'none' }} 
                          onChange={handleFabricFilesChange}
                        />
                      </div>

                      {fabricPreviews.length > 0 && (
                        <div className="uploaded-references-section">
                          <div className="section-subtitle">Uploaded Fabrics ({fabricPreviews.length}/10)</div>
                          <div className="references-grid">
                            {fabricPreviews.map((src, i) => (
                              <div className="reference-image-card" key={i}>
                                <img src={src} alt={`Fabric ${i+1}`} />
                                <button className="remove-image-btn" onClick={() => {
                                  setFabricPreviews(prev => prev.filter((_, idx) => idx !== i));
                                  setFabricFiles(prev => prev.filter((_, idx) => idx !== i));
                                }}>×</button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div>
                      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', overflowX: 'auto' }}>
                        {['All', 'Pure Silk', 'Zari Silk', 'Linen', 'Silk', 'Cotton'].map(cat => (
                          <button 
                            key={cat}
                            className={`tab-btn`} 
                            style={{ 
                              padding: '6px 12px', 
                              fontSize: '12px',
                              borderRadius: '99px',
                              border: '1px solid var(--border-color)',
                              background: fabricFilter === cat ? 'var(--text-primary)' : '#fff',
                              color: fabricFilter === cat ? '#fff' : 'var(--text-secondary)'
                            }}
                            onClick={() => setFabricFilter(cat)}
                          >
                            {cat}
                          </button>
                        ))}
                      </div>

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
                          <div style={{ fontWeight: 600 }}>Your fabric library is empty</div>
                          <div style={{ color: 'var(--text-secondary)', fontSize: '13px', maxWidth: '46ch', lineHeight: 1.5 }}>
                            Add the rolls you stock to pick from them here — or switch to
                            <strong> Customer's Own Fabric</strong> above if the client is bringing their own.
                          </div>
                          {/* Save first, then go. This button is the product's
                              own advice to a boutique with no fabric library --
                              and following it used to destroy the order being
                              written, because the wizard's only copy was in
                              this component's state. The draft is on the server
                              before we navigate, so the work is waiting when
                              they come back. */}
                          <button type="button" className="btn-secondary" onClick={async () => {
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
                            Save &amp; add fabrics
                          </button>
                        </div>
                      )}

                      <div className="fabrics-grid">
                        {fabrics
                          // Don't offer a roll the boutique has marked Out of
                          // Stock. Manage Fabrics renders that badge and lets
                          // the owner toggle it, but this grid consulted only
                          // the material filter -- so the owner could sell a
                          // fabric they had just told the system they had none
                          // of, with no signal on the card either way.
                          // Filtered here rather than in the viewset because
                          // Manage Fabrics legitimately needs the rows this
                          // hides; it is the screen that sets the flag.
                          .filter(f => f.is_available !== false)
                          .filter(f => fabricFilter === 'All' || f.material === fabricFilter)
                          .map(f => {
                            const resolvedImg = resolveMediaUrl(f.image_url);
                            return (
                              <div 
                                key={f.id} 
                                className={`fabric-card ${selectedFabric?.id === f.id ? 'selected' : ''}`}
                                onClick={() => {
                                  setSelectedFabric(f);
                                  setDrapingCompleted(false);
                                  setDrapingLoading(false);
                                }}
                              >
                                <div className="fabric-image-container">
                                  <img src={resolvedImg || 'https://images.unsplash.com/photo-1574169208507-84376144848b?w=400'} alt={f.name} onError={(e) => {
                                    e.target.src = 'https://images.unsplash.com/photo-1574169208507-84376144848b?w=400';
                                  }} />
                                  {selectedFabric?.id === f.id && (
                                    <div className="fabric-badge">
                                      <Check size={14} />
                                    </div>
                                  )}
                                </div>
                                <div className="fabric-details">
                                  <span className="fabric-title">{f.name} - {f.color}</span>
                                  <span className="fabric-price">{formatMoney(f.price_per_meter)} / mtr</span>
                                </div>
                              </div>
                            );
                          })}
                    </div>
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
                            onClick={() => {
                              setEditingTailor(null);
                              setTailorForm({ name: '', email: '', specialty: 'Ethnic & Bridal Cutting', rating: 5.0, status: 'Available', role: 'Master' });
                              setShowTailorModal(true);
                            }}
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
                            onClick={() => {
                              setEditingTailor(null);
                              setTailorForm({ name: '', email: '', specialty: 'Assembly & Detailing', rating: 5.0, status: 'Available', role: 'Tailor' });
                              setShowTailorModal(true);
                            }}
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
                      <p className="page-subtitle">Almost there! Please review your selections and order details. Once confirmed, we'll hand it over to your tailor and keep you updated at every step.</p>
                    </div>

                    <div className="accent-banner" style={{ margin: '4px 0 16px', backgroundColor: '#e2f5ec', borderColor: '#c3ebdb', color: '#107c41', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Check size={16} />
                      <span>All set! You're ready to create your order.</span>
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
                      <p className="page-subtitle">You're all set! Choose how you'd like to proceed with your payment. Pay now in full or pay partially and the remaining after design completion.</p>
                    </div>

                    <div className="accent-banner" style={{ margin: '4px 0 16px', backgroundColor: '#e2f5ec', borderColor: '#c3ebdb', color: '#107c41', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <ShieldCheck size={16} />
                      <span>Your order is safe and secure with Scaleezy.</span>
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
                      <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '16px' }}>Choose how you want to pay for your order.</p>

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
                              <p style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '4px' }}>Pay a part now to confirm your order. Pay the remaining after design is completed.</p>
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
      {view === 'confirmed' && confirmedOrder && (
        <div className="order-confirmed-container">
          <div className="success-badge-container">
            <div className="success-circle"><Check size={40} /></div>
            <h1 className="success-title">Your Order is Confirmed! 🎉</h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '15px' }}>
              Thank you, {customerForm.first_name}! We've received your order and our team has started working on your custom creation.
            </p>
            <div className="order-id-badge">
              <span>Order ID: <strong>{confirmedOrder.order_id}</strong></span>
              <button 
                aria-label="Copy order ID"
                title="Copy order ID"
                style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)', minWidth: '44px', minHeight: '44px', margin: '-12px' }}
                onClick={() => {
                  navigator.clipboard.writeText(confirmedOrder.order_id);
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
                { label: 'Stylist Review', desc: 'Your stylist is reviewing your order details.', active: true, completed: true },
                { label: 'Design & Creation', desc: 'Artisans will cut and assemble your custom garment.', active: false, completed: false },
                { label: 'Quality Check', desc: 'Multi-level measurement and stitching validation.', active: false, completed: false },
                { label: 'Packed & Shipped', desc: 'Packed securely and dispatched to your door.', active: false, completed: false }
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
      )}

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
              {ctaBusy ? t('wizard.working', 'Working…') : <>{currentStep === 5 ? t('wizard.confirmOrder', 'Confirm Order') : t('common.next', 'Next')}<ArrowRight size={16} /></>}
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
                  #invoice-printable, #invoice-printable * {
                    visibility: visible;
                  }
                  #invoice-printable {
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

              {/* Invoice Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '32px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  {boutiqueSettings?.logo && (
                    <img src={boutiqueSettings.logo} alt="Boutique Logo" style={{ maxHeight: '48px', objectFit: 'contain' }} />
                  )}
                  <div>
                    <h1 style={{ fontSize: '24px', fontWeight: 800, letterSpacing: '1px', color: '#0f291e', margin: 0 }}>
                      {boutiqueSettings?.name || "SCALEEZY"}
                    </h1>
                    <span style={{ fontSize: '10px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '1px' }}>Bespoke Atelier CRM</span>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, textTransform: 'uppercase', color: 'var(--text-secondary)' }}>INVOICE</h2>
                  <span style={{ fontSize: '12px', display: 'block', marginTop: '4px' }}>Invoice ID: <strong>{confirmedOrder.order_id}</strong></span>
                  <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginTop: '2px' }}>
                    Date: {fmtDate(confirmedOrder.order_date)}
                  </span>
                </div>
              </div>

              {/* Billed To / Designer Details */}
              <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '40px', borderTop: '1px solid #eaecef', borderBottom: '1px solid #eaecef', padding: '20px 0', marginBottom: '32px' }}>
                <div>
                  {/* Bill the customer this invoice is FOR. These fields used to
                      read customerForm -- the new-order wizard's state -- which
                      is empty or stale when the invoice is opened from the
                      Invoices tab, because that button sets only
                      confirmedOrder. The printed invoice then carried a
                      different client's name, address, phone and email while
                      showing the right order id and total: a wrong bill and a
                      disclosure of one customer's details to another. */}
                  <span style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>Billed To:</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, display: 'block' }}>{confirmedOrder.customer_name}</span>
                  <span style={{ display: 'block', color: 'var(--text-secondary)', marginTop: '4px' }}>{confirmedOrder.delivery_address || confirmedOrder.customer_address}</span>
                  <span style={{ display: 'block', color: 'var(--text-secondary)' }}>📞 {formatMobile(confirmedOrder.customer_mobile)}</span>
                  {confirmedOrder.customer_email && <span style={{ display: 'block', color: 'var(--text-secondary)' }}>✉️ {confirmedOrder.customer_email}</span>}
                </div>
                <div>
                  <span style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>Atelier Details:</span>
                  {/* No vendor fallbacks on the customer's copy. These printed
                      "123 Atelier Way, Fashion District" and
                      "contact@scaleezy.com" as the BOUTIQUE'S OWN details on an
                      invoice handed to a real customer -- our demo strings, in
                      their name, telling them to pay and collect somewhere that
                      does not exist. A blank line is the honest failure: it
                      shows the owner something is missing from their profile,
                      and shows the customer nothing false. */}
                  <span style={{ fontSize: '14px', fontWeight: 700, display: 'block' }}>{boutiqueSettings?.name || ''}</span>
                  {boutiqueSettings?.address && (
                    <span style={{ display: 'block', color: 'var(--text-secondary)', marginTop: '4px' }}>📍 {boutiqueSettings.address}</span>
                  )}
                  {boutiqueSettings?.phone && (
                    <span style={{ display: 'block', color: 'var(--text-secondary)' }}>📞 {boutiqueSettings.phone}</span>
                  )}
                  {boutiqueSettings?.email && (
                    <span style={{ display: 'block', color: 'var(--text-secondary)' }}>✉️ {boutiqueSettings.email}</span>
                  )}
                  <span style={{ display: 'block', color: 'var(--text-secondary)', marginTop: '4px' }}>Boutique Owner: {currentUser?.first_name || 'Aditi'} {currentUser?.last_name || 'Mehta'}</span>
                  {confirmedOrder.tailor_name && (
                    <span style={{ display: 'block', color: 'var(--text-secondary)', marginTop: '4px' }}>
                      Assigned Tailor: <strong>{confirmedOrder.tailor_name}</strong>
                    </span>
                  )}
                  <span style={{ display: 'block', color: 'var(--text-secondary)' }}>Estimated Delivery: {fmtDate(confirmedOrder.estimated_delivery)}</span>
                </div>
              </div>

              {/* Garment Details Summary */}
              <div style={{ backgroundColor: '#fcfdfd', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '16px', marginBottom: '32px' }}>
                <h4 style={{ fontSize: '12px', fontWeight: 700, margin: '0 0 12px 0', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Design & Specifications</h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', fontSize: '11px' }}>
                  <div>
                    <span style={{ color: 'var(--text-secondary)', display: 'block' }}>
                      {orderGarmentNames(confirmedOrder).length > 1 ? 'Garments' : 'Garment Type'}
                    </span>
                    <strong style={{ fontSize: '12px' }}>{confirmedOrder.customer_type} • {orderGarmentLabel(confirmedOrder)}</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Fabric</span>
                    <strong style={{ fontSize: '12px' }}>
                      {/* Priced from the order, so it is right whichever screen
                          opened this invoice. A zero fabric charge is what
                          "customer brought their own" looks like on the bill. */}
                      {Number(confirmedOrder.fabric_price) > 0 ? `₹${confirmedOrder.fabric_price}` : 'Customer Fabric'}
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Occasion</span>
                    <strong style={{ fontSize: '12px' }}>{confirmedOrder.customer_occasion || '—'}</strong>
                  </div>
                  {confirmedOrder.customer_neckline_style && (
                    <div>
                      <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Neckline Style</span>
                      <strong>{confirmedOrder.customer_neckline_style}</strong>
                    </div>
                  )}
                  {confirmedOrder.customer_sleeve_style && (
                    <div>
                      <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Sleeve Style</span>
                      <strong>{confirmedOrder.customer_sleeve_style}</strong>
                    </div>
                  )}
                  {confirmedOrder.customer_back_style && (
                    <div>
                      <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Back Style</span>
                      <strong>{confirmedOrder.customer_back_style}</strong>
                    </div>
                  )}
                </div>
              </div>

              {/* Pricing Table */}
              <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '32px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #eaecef', fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
                    <th style={{ padding: '12px 8px', fontWeight: 600 }}>Description</th>
                    <th style={{ padding: '12px 8px', fontWeight: 600, textAlign: 'right' }}>Amount</th>
                  </tr>
                </thead>
                <tbody style={{ fontSize: '12px' }}>
                  {/* One priced line per garment -- the day the old ponytail
                      note here waited for. Each row is that job's own
                      components summed; orders from before per-garment pricing
                      have all-zero jobs and keep the single combined line, so
                      an old invoice reprints exactly as it was issued. */}
                  {(() => {
                    const jobs = confirmedOrder.garment_jobs || [];
                    const jobTotal = (job) =>
                      ['base_price', 'fabric_price', 'embroidery_price',
                       'customization_price', 'tailoring_charges']
                        .reduce((sum, key) => sum + parseFloat(job[key] || 0), 0);
                    const priced = jobs.filter(job => jobTotal(job) > 0);
                    if (!priced.length) {
                      return (
                        <tr style={{ borderBottom: '2px solid #eaecef' }}>
                          <td style={{ padding: '16px 8px' }}>
                            <strong style={{ fontSize: '14px', color: '#0f291e' }}>
                              Bespoke Handcrafted {orderGarmentLabel(confirmedOrder)}
                            </strong>
                            <span style={{ display: 'block', fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                              {orderGarmentNames(confirmedOrder).length > 1
                                ? `${orderGarmentNames(confirmedOrder).length} custom garments, each tailored to its own measurement specifications.`
                                : 'Custom garment design tailored to individual measurement specifications.'}
                            </span>
                            <span style={{ display: 'block', fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                              Fabric: {Number(confirmedOrder.fabric_price) > 0 ? `Boutique fabric — ₹${confirmedOrder.fabric_price}` : 'Customer Supplied Fabric'}
                            </span>
                          </td>
                          {/* Before tax, matching the Subtotal row below. */}
                          <td style={{ padding: '16px 8px', textAlign: 'right', fontWeight: 700, fontSize: '14px' }}>
                            {formatMoney(Number(confirmedOrder.total_amount || 0) - Number(confirmedOrder.taxes || 0))}
                          </td>
                        </tr>
                      );
                    }
                    return (
                      <>
                        {priced.map(job => (
                          <tr key={job.id} style={{ borderBottom: '1px solid #eaecef' }}>
                            <td style={{ padding: '12px 8px' }}>
                              <strong style={{ fontSize: '13px', color: '#0f291e' }}>
                                Bespoke Handcrafted {job.template_name || 'Garment'}
                              </strong>
                              <span style={{ display: 'block', fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                                {parseFloat(job.fabric_price || 0) > 0
                                  ? `Includes boutique fabric — ${formatMoney(job.fabric_price)}`
                                  : 'Customer supplied fabric'}
                              </span>
                            </td>
                            <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 700, fontSize: '13px' }}>
                              {formatMoney(jobTotal(job))}
                            </td>
                          </tr>
                        ))}
                        {parseFloat(confirmedOrder.packaging_handling || 0) > 0 && (
                          <tr style={{ borderBottom: '1px solid #eaecef' }}>
                            <td style={{ padding: '12px 8px', fontSize: '12px' }}>Packaging & Handling</td>
                            <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 600, fontSize: '12px' }}>
                              {formatMoney(confirmedOrder.packaging_handling)}
                            </td>
                          </tr>
                        )}
                        {parseFloat(confirmedOrder.discount || 0) > 0 && (
                          <tr style={{ borderBottom: '2px solid #eaecef' }}>
                            <td style={{ padding: '12px 8px', fontSize: '12px' }}>Discount</td>
                            <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 600, fontSize: '12px', color: '#107c41' }}>
                              −{formatMoney(confirmedOrder.discount)}
                            </td>
                          </tr>
                        )}
                      </>
                    );
                  })()}
                </tbody>
              </table>

              {/* Subtotal & Taxes Breakdown */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', fontSize: '12px' }}>
                <div style={{ width: '250px' }}>
                  {/* The 5% tax is charged and stored, and the invoice showed
                      only the gross total -- so the one document the customer
                      keeps did not say what the tax was. Both figures are
                      already on the payload. */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '11px', color: 'var(--text-secondary)' }}>
                    <span>Subtotal</span>
                    <strong style={{ fontWeight: 600 }}>
                      {formatMoney(Number(confirmedOrder.total_amount || 0) - Number(confirmedOrder.taxes || 0))}
                    </strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '11px', color: 'var(--text-secondary)' }}>
                    <span>Taxes (GST 5%)</span>
                    <strong style={{ fontWeight: 600 }}>{formatMoney(confirmedOrder.taxes)}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 0 6px 0', borderTop: '2px solid #0f291e', fontSize: '16px' }}>
                    <span style={{ fontWeight: 700, color: '#0f291e' }}>Total Amount</span>
                    <strong style={{ fontWeight: 800, color: '#107c41' }}>{formatMoney(confirmedOrder.total_amount)}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '11px', color: 'var(--text-secondary)', borderTop: '1px solid #eaecef', marginTop: '6px' }}>
                    <span>Payment Status</span>
                    <strong style={{ fontWeight: 600 }}>{confirmedOrder.payment_status}</strong>
                  </div>
                  {/* Keyed on amount_paid, not advance_paid.
                      The advance is only what was taken up front, and
                      _reconcile_payment merely CAPS it as later payments land --
                      so a settled order kept its original advance while
                      amount_paid reached the total, and the invoice printed
                      "Payment Status: Paid" directly above "Advance Paid
                      ₹10,000 / Balance Due ₹23,075". Reachable for any existing
                      order through Invoices → View Invoice, which is the copy
                      that gets handed to the customer.
                      Balance Due now uses the same expression as the Invoices
                      table and the customer tracking page, so the three cannot
                      disagree about what is owed. */}
                  {parseFloat(confirmedOrder.amount_paid || 0) > 0 && (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '11px', color: 'var(--text-secondary)' }}>
                        <span>Paid</span>
                        <strong style={{ fontWeight: 600 }}>{formatMoney(confirmedOrder.amount_paid)}</strong>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '11px', color: 'var(--text-secondary)' }}>
                        <span>Balance Due</span>
                        <strong style={{ fontWeight: 600 }}>{formatMoney(Math.max(0, Number(confirmedOrder.total_amount || 0) - Number(confirmedOrder.amount_paid || 0)))}</strong>
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Terms Footer */}
              <div style={{ borderTop: '1px solid #eaecef', marginTop: '48px', paddingTop: '20px', textAlign: 'center', fontSize: '10px', color: 'var(--text-secondary)' }}>
                <p style={{ margin: '0 0 4px 0' }}>Thank you for creating your bespoke order with **SCALEEZY** Atelier.</p>
                <p style={{ margin: 0 }}>This is a computer-generated invoice and does not require a physical signature.</p>
              </div>
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
      {activeReviewStage && activeReviewOrder && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1100
        }}>
          <div style={{
            backgroundColor: 'var(--surface-color)',
            borderRadius: '12px',
            border: '1px solid var(--border-color)',
            width: '500px',
            maxWidth: '95%',
            padding: '24px',
            boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
            display: 'flex',
            flexDirection: 'column',
            gap: '20px',
            maxHeight: '90vh',
            overflowY: 'auto'
          }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 600, margin: 0, fontFamily: 'var(--font-serif)' }}>
                  {selectedStageObj ? `Production Stage: ${selectedStageObj.stage_name}` : `Stage Review: ${activeReviewStage}`}
                </h3>
                <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Order ID: {activeReviewOrder.order_id}</span>
              </div>
              <button 
                className="btn-secondary" 
                style={{ padding: '4px 10px', fontSize: '12px' }}
                onClick={() => {
                  setActiveReviewStage(null);
                  setActiveReviewOrder(null);
                  setSelectedStageObj(null);
                  setSelectedPerformerId('');
                }}
              >
                Close
              </button>
            </div>

            {/* What is actually being made. The wizard collects a full spec and
                measurement snapshot per dress and saved it correctly -- and
                then no screen ever read it back, so the person opening this
                stage to cut or stitch the garment could not see what the
                customer had asked for. Nested on the order payload, so it
                needs no fetch of its own. */}
            {(activeReviewOrder.garment_jobs || []).length > 0 && (
              <div style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '8px', fontSize: '12px' }}>
                <div style={{ fontWeight: 700, marginBottom: '8px' }}>What to make</div>
                {activeReviewOrder.garment_jobs.map(job => {
                  // Material fields are rendered from job.materials, which
                  // carries the item's name, quantity and unit. Left in the spec
                  // dump they printed as bare database UUIDs -- "main fabric:
                  // a1222bee-8dea-442d-9858-524141b109c4" -- on the one screen
                  // a cutter opens to find out which roll to pull.
                  const materials = job.materials || [];
                  const materialKeys = new Set(materials.map(m => m.field_key));
                  const specEntries = Object.entries(job.spec || {})
                    .filter(([k, v]) => v !== '' && v !== null && v !== undefined
                                        && !materialKeys.has(k));
                  return (
                    <div key={job.id} style={{ marginBottom: '10px' }}>
                      <div style={{ fontWeight: 600, marginBottom: '4px' }}>{job.template_name || job.template_key}</div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '4px 12px' }}>
                        {Object.entries(job.measurements || {}).map(([k, v]) => (
                          <span key={k} style={{ color: 'var(--text-secondary)' }}>
                            {humaniseSpecKey(k)}: <strong style={{ color: 'var(--text-primary)' }}>{String(v)} in</strong>
                          </span>
                        ))}
                        {specEntries.map(([k, v]) => (
                          <span key={k} style={{ color: 'var(--text-secondary)' }}>
                            {humaniseSpecKey(k)}: <strong style={{ color: 'var(--text-primary)' }}>{humaniseSpecValue(v)}</strong>
                          </span>
                        ))}
                      </div>
                      {materials.length > 0 && (
                        <div style={{ marginTop: '6px' }}>
                          <div style={{ fontWeight: 600, marginBottom: '2px' }}>Materials</div>
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '4px 12px' }}>
                            {materials.map(material => (
                              <span key={material.id} style={{ color: 'var(--text-secondary)' }}>
                                {humaniseSpecKey(material.field_key)}:{' '}
                                <strong style={{ color: 'var(--text-primary)' }}>
                                  {material.item_name || material.free_text || '—'}
                                </strong>
                                {Number(material.quantity) > 0
                                  && ` · ${Number(material.quantity)} ${material.unit || ''}`.trimEnd()}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
                {activeReviewOrder.special_instructions && (
                  <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid var(--border-color)' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Special instructions: </span>
                    <strong>{activeReviewOrder.special_instructions}</strong>
                  </div>
                )}
              </div>
            )}

            {/* The approved design, and the Master's note on how to make it.
                GET /design-studio/boards/ has always served this and even swaps
                in TailorBriefSerializer for a Tailor -- but api.getDesignBoards
                had zero callers, so the design the owner approved reached the
                person stitching it through no screen at all. The notes box
                lives here because the endpoint that writes it had nowhere to be
                called from until the board was on screen. */}
            {stageDesignBrief && stageDesignBrief.design && (
              <div style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '8px', fontSize: '12px' }}>
                <div style={{ fontWeight: 700, marginBottom: '8px' }}>Approved design</div>
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
              </div>
            )}

            {/* Stage Info Details */}
            {selectedStageObj && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '8px', fontSize: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Current Status:</span>
                  <span style={{
                    fontWeight: 700,
                    color: selectedStageObj.status === 'COMPLETED' ? '#10b981' : selectedStageObj.status === 'IN_PROGRESS' ? '#3b82f6' : selectedStageObj.status === 'PAUSED' ? '#f59e0b' : '#777'
                  }}>{selectedStageObj.status.toUpperCase()}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>SLA / Target Time:</span>
                  <span>{selectedStageObj.sla_hours} Hours</span>
                </div>
                {selectedStageObj.started_at && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Started At:</span>
                    <span>{new Date(selectedStageObj.started_at).toLocaleString()}</span>
                  </div>
                )}
                {selectedStageObj.completed_at && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Completed At:</span>
                    <span>{new Date(selectedStageObj.completed_at).toLocaleString()}</span>
                  </div>
                )}
                {selectedStageObj.duration_seconds > 0 && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Actual Duration:</span>
                    <span>{(() => {
                      const mins = Math.floor(selectedStageObj.duration_seconds / 60);
                      const hrs = Math.floor(mins / 60);
                      if (hrs > 0) return `${hrs}h ${mins % 60}m`;
                      return `${mins}m`;
                    })()}</span>
                  </div>
                )}
                {selectedStageObj.performed_by_name && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Assigned Performer:</span>
                    <span><strong>{selectedStageObj.performed_by_name}</strong></span>
                  </div>
                )}
              </div>
            )}

            {/* Existing Stage Feedbacks / Notes */}
            {selectedStageObj && selectedStageObj.comments && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', border: '1px solid var(--border-color)', padding: '12px', borderRadius: '8px', background: 'rgba(255,255,255,0.01)' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600 }}>Active Notes / Logs:</span>
                <p style={{ fontSize: '12px', fontStyle: 'italic', margin: 0 }}>"{selectedStageObj.comments}"</p>
              </div>
            )}

            {/* Photo Gallery for Stage Attachments */}
            {selectedStageObj && selectedStageObj.attachments && selectedStageObj.attachments.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600 }}>Progress Photos ({selectedStageObj.attachments.length}):</span>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(80px, 1fr))', gap: '8px' }}>
                  {selectedStageObj.attachments.map((url, i) => (
                    <a key={i} href={url} target="_blank" rel="noreferrer">
                      <img src={url} alt={`attachment-${i}`} style={{ width: '80px', height: '80px', objectFit: 'cover', borderRadius: '4px', border: '1px solid var(--border-color)' }} />
                    </a>
                  ))}
                </div>
              </div>
            )}

            {/* Submit New Transition / Action controls */}
            <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                Manage Stage Transition
              </h4>

              {/* Hand this stage to someone, ahead of the work starting.
                  assign_stage is in SUPERVISOR_ORDER_ACTIONS specifically so a
                  Master can delegate -- "handing work to someone else is a
                  supervisor's call" -- and the API honours it, but the only
                  Assign control in the product was gated to Owner AND lived on
                  the overview tab, which a Master's nav does not contain and
                  login never routes them to. The capability was granted and
                  unreachable. Here it sits on the screen a Master actually
                  works from. */}
              {selectedStageObj && (!currentUser.role || currentUser.role === 'Owner'
                || SUPERVISOR_ROLES.includes(currentUser.role)) && (
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                    Assign this stage to
                  </label>
                  <select
                    className="form-control"
                    style={{ fontSize: '12px', padding: '6px' }}
                    value={selectedStageObj.assigned_to || ''}
                    disabled={assigningStageKey === selectedStageObj.stage_key}
                    onChange={(e) => handleAssignStage(
                      activeReviewOrder.id, selectedStageObj.stage_key, e.target.value)}
                  >
                    <option value="">Unassigned</option>
                    {eligibleStaffForStage(selectedStageObj.stage_key).map(t => (
                      <option key={t.id} value={t.id}>{t.name} · {t.role}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Who actually did the work, recorded with the transition. This
                  is a different question from who it was assigned to, and it
                  used to offer every member of staff regardless of whether the
                  stage's role list permits them -- so it wrote a pairing that
                  assign-stage refuses with a 400. */}
              {(!currentUser.role || currentUser.role === 'Owner'
                || SUPERVISOR_ROLES.includes(currentUser.role)) && (
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Record who performed this</label>
                  <select
                    className="form-control"
                    style={{ fontSize: '12px', padding: '6px' }}
                    value={selectedPerformerId}
                    onChange={(e) => setSelectedPerformerId(e.target.value)}
                  >
                    <option value="">-- Select Tailor / Master --</option>
                    {(selectedStageObj
                      ? eligibleStaffForStage(selectedStageObj.stage_key)
                      : tailors).map(t => (
                      <option key={t.id} value={t.id}>{t.name} ({t.role})</option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Comments / Fitting Logs</label>
                <textarea 
                  className="form-control"
                  style={{ height: '60px', fontSize: '12px' }}
                  placeholder="Enter notes, alterations details, or comments..."
                  value={stageReviewComments}
                  onChange={(e) => setStageReviewComments(e.target.value)}
                />
              </div>

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Upload Progress Photo</label>
                <input 
                  type="file" 
                  className="form-control"
                  style={{ fontSize: '12px' }}
                  accept="image/*"
                  onChange={(e) => setStageReviewImage(e.target.files[0])}
                />
              </div>

              {/* Action Buttons Panel */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '10px', marginTop: '10px' }}>
                {selectedStageObj && (selectedStageObj.status === 'NOT_STARTED' || selectedStageObj.status === 'PAUSED') && (
                  <button 
                    className="btn-primary" 
                    style={{ background: '#3b82f6', color: '#fff', fontSize: '12px', padding: '8px' }}
                    onClick={async () => {
                      try {
                        await api.transitionStage(
                          activeReviewOrder.id,
                          selectedStageObj.stage_key,
                          'IN_PROGRESS',
                          stageReviewComments,
                          stageReviewImage ? [stageReviewImage] : [],
                          selectedPerformerId || null
                        );
                        alert("Stage started successfully!");
                        setActiveReviewStage(null);
                        setActiveReviewOrder(null);
                        setSelectedStageObj(null);
                        setSelectedPerformerId('');
                        fetchDashboardAndConfig();
                      } catch (err) {
                        alert("Failed to transition: " + err.message);
                      }
                    }}
                  >
                    Start In-Progress
                  </button>
                )}

                {selectedStageObj && selectedStageObj.status === 'IN_PROGRESS' && (
                  <>
                    <button 
                      className="btn-secondary" 
                      style={{ background: '#f59e0b', color: '#fff', border: 'none', fontSize: '12px', padding: '8px' }}
                      onClick={async () => {
                        try {
                          await api.transitionStage(
                            activeReviewOrder.id,
                            selectedStageObj.stage_key,
                            'PAUSED',
                            stageReviewComments,
                            stageReviewImage ? [stageReviewImage] : [],
                            selectedPerformerId || null
                          );
                          alert("Stage paused successfully!");
                          setActiveReviewStage(null);
                          setActiveReviewOrder(null);
                          setSelectedStageObj(null);
                          setSelectedPerformerId('');
                          fetchDashboardAndConfig();
                        } catch (err) {
                          alert("Failed to transition: " + err.message);
                        }
                      }}
                    >
                      Pause Stage
                    </button>
                    <button 
                      className="btn-primary" 
                      style={{ background: '#10b981', color: '#fff', fontSize: '12px', padding: '8px' }}
                      onClick={async () => {
                        try {
                          await api.transitionStage(
                            activeReviewOrder.id,
                            selectedStageObj.stage_key,
                            'COMPLETED',
                            stageReviewComments,
                            stageReviewImage ? [stageReviewImage] : [],
                            selectedPerformerId || null
                          );
                          alert("Stage completed successfully!");
                          setActiveReviewStage(null);
                          setActiveReviewOrder(null);
                          setSelectedStageObj(null);
                          setSelectedPerformerId('');
                          fetchDashboardAndConfig();
                        } catch (err) {
                          alert("Failed to transition: " + err.message);
                        }
                      }}
                    >
                      Complete Stage
                    </button>
                  </>
                )}

                {selectedStageObj && selectedStageObj.status !== 'COMPLETED' && selectedStageObj.status !== 'SKIPPED' && (
                  <button 
                    className="btn-secondary" 
                    style={{ fontSize: '12px', padding: '8px' }}
                    onClick={async () => {
                      try {
                        await api.transitionStage(
                          activeReviewOrder.id,
                          selectedStageObj.stage_key,
                          'SKIPPED',
                          stageReviewComments,
                          stageReviewImage ? [stageReviewImage] : [],
                          selectedPerformerId || null
                        );
                        alert("Stage skipped successfully!");
                        setActiveReviewStage(null);
                        setActiveReviewOrder(null);
                        setSelectedStageObj(null);
                        setSelectedPerformerId('');
                        fetchDashboardAndConfig();
                      } catch (err) {
                        alert("Failed to transition: " + err.message);
                      }
                    }}
                  >
                    Skip Stage
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

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
    </div>
  );
}

export default App;
