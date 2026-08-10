import React, { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { 
  Users, ShoppingBag, Scissors, Search, 
  Upload, Check, ArrowRight, ArrowLeft, Heart, 
  MessageSquare, Star, Copy, ShieldCheck, Compass, BarChart2,
  FolderOpen, Sparkles, HelpCircle, X, ExternalLink,
  ChevronRight, Lock, Mail, Phone, Calendar, Landmark, 
  FileText, Bell, User, MapPin, Eye, EyeOff, Edit2, Plus, Trash2, LogOut, History, Package, Menu
} from 'lucide-react';
import { api } from './services/api';
import { resolveMediaUrl } from './services/media';
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
import TemplateForm from './features/catalog/TemplateForm';
import GarmentSummary from './features/catalog/GarmentSummary';
import { MobileHeader } from './components/ui/MobileHeader';
import { BottomNavigation } from './components/ui/BottomNavigation';
import { BottomSheet } from './components/ui/BottomSheet';
import { ResponsiveCard } from './components/ui/ResponsiveCard';
import { ProgressiveAccordion } from './components/ui/ProgressiveAccordion';

/** Placeholder shown while a lazily loaded screen arrives. */
const ScreenLoading = () => (
  <div style={{ padding: '48px', textAlign: 'center', color: '#8a8a8a' }}>Loading...</div>
);
import { splitSpec, validateSpec } from './services/templates';

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
        <span style={{ fontSize: '13px', fontWeight: 600 }}>Finished garment photos</span>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          {published ? 'visible to the customer' : `${images.length} uploaded, not yet shared`}
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
                Remove
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
          {busy ? 'Working…' : 'Add photo'}
        </button>

        <button
          type="button"
          className="btn-secondary"
          style={{ fontSize: '12px', padding: '6px 10px' }}
          disabled={busy || (!published && missing.length > 0)}
          title={missing.length ? `Still needs: ${missing.join(', ')}` : ''}
          onClick={() => run(() => api.publishGarmentImages(order.id, !published))}
        >
          {published ? 'Hide from customer' : 'Share with customer'}
        </button>

        {!published && missing.length > 0 && (
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            needs {missing.map((m) => m.toLowerCase()).join(' and ')}
          </span>
        )}
      </div>
    </div>
  );
}

function StageTimeline({ stages, onSelectStage }) {
  if (!stages || stages.length === 0) {
    return (
      <div style={{
        margin: '8px 0', padding: '12px 16px', background: 'var(--surface-color)',
        borderRadius: '8px', border: '1px solid var(--border-color)',
        fontSize: '12px', color: 'var(--text-muted)', textAlign: 'center'
      }}>
        No production stages recorded for this order.
      </div>
    );
  }

  return (
    <div style={{
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
            role="button"
            tabIndex={0}
            title={`${stage.stage_name} — ${stage.status.replace('_', ' ').toLowerCase()}`}
            style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: '95px', cursor: 'pointer' }}
            onClick={() => onSelectStage(stage)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectStage(stage); } }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px', flex: 1 }}>
              <div style={{
                width: '10px', height: '10px', borderRadius: '50%',
                backgroundColor: statusColor,
                border: isInProgress ? '2px solid #fff' : 'none',
                boxShadow: isInProgress ? '0 0 0 2px #3b82f6' : 'none'
              }} />
              <span style={{
                fontSize: '9px',
                fontWeight: isInProgress ? 700 : 500,
                color: isCompleted ? '#10b981' : isInProgress ? '#3b82f6' : 'var(--text-muted)',
                textAlign: 'center', whiteSpace: 'nowrap'
              }}>
                {stage.stage_name}
              </span>
            </div>
            {idx < arr.length - 1 && (
              <div style={{
                height: '2px', flex: 1,
                backgroundColor: isCompleted ? '#10b981' : 'var(--border-color)',
                minWidth: '10px', marginTop: '-14px'
              }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function App() {
  // The marketing site is static HTML at / and no longer a view in here -- see
  // frontend/index.html. This bundle is the workspace, served from /app, so it
  // opens on the sign-in screen and "back" links leave for the marketing site.
  const [view, setView] = useState('login'); // 'login', 'signup', 'dashboard', 'order-selector', 'wizard', 'confirmed'
  const [dashboardTab, setDashboardTab] = useState('overview'); // 'overview', 'fabrics', 'tailors', 'designs'
  const [currentUser, setCurrentUser] = useState(null);
  
  // Login Form State
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);

  // Signup Wizard State
  const [signupStep, setSignupStep] = useState(1); // 1: Account, 2: Verify, 3: Profile, 4: Prefs, 5: Complete
  const [signupForm, setSignupForm] = useState({
    first_name: '',
    last_name: '',
    email_address: '',
    mobile_number: '',
    password: ''
  });
  const [otpCode, setOtpCode] = useState('');
  const [profileOccupation, setProfileOccupation] = useState('');
  const [profileComm, setProfileComm] = useState('WhatsApp');

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
  const [quotePrices, setQuotePrices] = useState({
    base: 0,
    fabric: 0,
    embroidery: 7500,
    customization: 2500,
    tailoring: 5000,
    packaging: 500
  });
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

  // Sync quote prices dynamically based on Garment and Fabric selections
  useEffect(() => {
    const base = GARMENT_PRICES[customerForm.garment_type] || 15000;
    const fabric = fabricTab === 'boutique' && selectedFabric ? parseFloat(selectedFabric.price_per_meter) * 3 : 0.00;
    setQuotePrices(prev => ({
      ...prev,
      base,
      fabric
    }));
  }, [customerForm.garment_type, selectedFabric, fabricTab]);

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
      setGarmentJobs(prev => [...prev, { key, template, values: {} }]);
    } catch (err) {
      console.error(err);
      alert('Could not load that garment form.');
    }
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

  /** Validate every dress on the order; returns true when all of them pass. */
  const validateGarments = ({ partial = false } = {}) => {
    const errors = {};
    garmentJobs.forEach(job => {
      const jobErrors = validateSpec(job.template, job.values, { partial });
      if (Object.keys(jobErrors).length) errors[job.key] = jobErrors;
    });
    setGarmentErrors(errors);
    return Object.keys(errors).length === 0;
  };

  /** Persist one GarmentJob per dress once the order exists to hang them on. */
  const saveGarmentJobs = async (orderId) => {
    for (const job of garmentJobs) {
      const { spec, measurements } = splitSpec(job.template, job.values);
      try {
        await api.createGarmentJob({
          order: orderId,
          template: job.template.id,
          spec,
          measurements,
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

  // Persisted Session check
  useEffect(() => {
    checkAuthSession();
  }, []);

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
          setDashboardTab('designs');
          return;
        }
        if (user.role === 'Master' || user.role === 'Tailor') {
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
      load('settings', api.getBoutiqueSettings, setBoutiqueSettings),
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
      if (editingTailor) {
        await api.updateTailor(editingTailor.id, payload);
      } else {
        await api.createTailor(payload);
      }
      setShowTailorModal(false);
      setEditingTailor(null);
      setTailorForm({ name: '', email: '', specialty: '', rating: 5.0, status: 'Available', role: 'Tailor' });
      fetchDashboardAndConfig();
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
    try {
      const res = await api.login(loginEmail, loginPassword);
      setCurrentUser(res.user);
      setView('dashboard');
      if (res.user.role === 'Designer') {
        // See the matching branch in checkAuthSession for why this skips
        // fetchDashboardAndConfig entirely rather than fetching and hiding.
        setDashboardTab('designs');
        return;
      }
      if (res.user.role === 'Master' || res.user.role === 'Tailor') {
        setDashboardTab('assignments');
      } else {
        setDashboardTab('overview');
      }
      fetchDashboardAndConfig(res.user);
    } catch (err) {
      alert(err.message || "Invalid credentials.");
    }
  };

  const handleSignupSubmit = async (e) => {
    e.preventDefault();
    if (!signupForm.first_name || !signupForm.last_name || !signupForm.email_address || !signupForm.password) {
      alert("Please enter all required signup fields.");
      return;
    }
    setSignupStep(2); // Mock verification
  };

  const handleVerifyOTP = async () => {
    if (!otpCode) {
      alert("Please enter the verification code sent to your phone/email.");
      return;
    }
    setSignupStep(3); // Enter profile info
  };

  const handleProfileSubmit = () => {
    setSignupStep(4); // Select preferences
  };

  const handleCompleteRegistration = async () => {
    try {
      const res = await api.signup({
        first_name: signupForm.first_name,
        last_name: signupForm.last_name,
        email_address: signupForm.email_address,
        mobile_number: signupForm.mobile_number,
        password: signupForm.password,
        occupation: profileOccupation,
        preferred_communication: profileComm
      });
      setCurrentUser(res.user);
      setSignupStep(5);
      setTimeout(() => {
        setView('dashboard');
        fetchDashboardAndConfig(res.user);
      }, 1500);
    } catch (err) {
      alert(err.message || "Registration failed.");
      setSignupStep(1);
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
    // Name, email, phone and address are what the boutique needs to reach the
    // customer and deliver to them. Everything else on this form is optional --
    // city and source used to be starred but were never actually enforced, so
    // the asterisks were telling staff something untrue.
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
    
    try {
      if (customerId) {
        const res = await api.updateCustomer(customerId, customerForm);
        return res;
      } else {
        const res = await api.createCustomer(customerForm, profilePhoto);
        setCustomerId(res.id);
        return res;
      }
    } catch (err) {
      let errMsg = err.message;
      try {
        const parsed = JSON.parse(err.message);
        if (parsed.mobile_number) {
          errMsg = `Mobile Number: ${parsed.mobile_number.join(', ')}`;
        } else if (parsed.email_address) {
          errMsg = `Email: ${parsed.email_address.join(', ')}`;
        } else {
          errMsg = Object.keys(parsed).map(k => `${k}: ${parsed[k]}`).join('\n');
        }
      } catch (e) {
        // Use default errMsg
      }
      alert("Failed to save customer: " + errMsg);
      throw err;
    }
  };

  const saveStep2 = async () => {
    if (!customerId) return;
    // The customer record keeps the body measurements, which is what the
    // directory, the measurement history and the design studio read. Per-dress
    // numbers live on the garment job; these are the ones that describe the
    // person, so the newest dress that carries them wins.
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
    const res = await api.updateCustomer(customerId, { measurements: body });
    return res;
  };

  const saveStep3 = async () => {
    if (!customerId) return;
    const links = designLinks
      .split(/[\n,]/)
      .map(l => l.trim())
      .filter(Boolean);
    const res = await api.saveDesignPreferences(
      customerId, designNotes, designFiles, selectedDesignTemplates, designSource, links
    );
    return res;
  };

  const saveStep4 = async () => {
    if (!customerId) return;
    
    let fabricPayload = {
      is_boutique_fabric: fabricTab === 'boutique',
      fabric_name: fabricTab === 'boutique' && selectedFabric ? selectedFabric.name : 'Customer Uploaded Fabric',
      fabric_price: fabricTab === 'boutique' && selectedFabric ? selectedFabric.price_per_meter * 3 : 0.00
    };

    const res = await api.saveFabricSelection(customerId, fabricPayload, fabricFiles);
    return res;
  };

  const submitOrderAndConfirm = async () => {
    if (!customerId) return;
    
    const base = parseFloat(quotePrices.base || 0);
    const fabricPrice = parseFloat(quotePrices.fabric || 0);
    const embroidery = parseFloat(quotePrices.embroidery || 0);
    const customization = parseFloat(quotePrices.customization || 0);
    const tailoring = parseFloat(quotePrices.tailoring || 0);
    const packaging = parseFloat(quotePrices.packaging || 0);

    const payload = {
      tailor_id: selectedTailor ? selectedTailor.id : null,
      master_id: selectedMaster ? selectedMaster.id : null,
      base_price: base,
      fabric_price: fabricPrice,
      embroidery_price: embroidery,
      customization_price: customization,
      tailoring_charges: tailoring,
      packaging_handling: packaging,
      payment_status: paymentOption === 'full' ? 'Paid' : 'Partially Paid',
      advance_paid: paymentOption === 'full' ? getTotalPrice() : (parseFloat(advancePaymentAmount) || getTotalPrice() / 2),
      custom_requirements: specialInstructions || customerForm.custom_requirements,
      // The earliest date any dress on this order is due -- an order is only as
      // early as its slowest-promised garment is late, so the soonest date is
      // the one the customer must not be told wrong. Omitted when no garment
      // carries a date, and the server falls back to its own estimate.
      estimated_delivery: garmentJobs
        .map(j => j.values?.delivery_date)
        .filter(Boolean)
        .sort()[0] || null,
      delivery_method: deliveryMethod,
      courier_service: deliveryMethod === 'Courier' ? courierService : null,
      tracking_number: deliveryMethod === 'Courier' ? trackingNumber : null,
      delivery_address: deliveryMethod === 'Courier' ? deliveryAddress : null
    };

    try {
      const order = await api.createOrder(customerId, payload);
      // Every dress on the order, with its own spec and measurement snapshot.
      // Written before the confirmation screen so a failure here is visible
      // rather than leaving an order with no garment on it.
      await saveGarmentJobs(order.id);
      // The design board is built in step 3, before an order exists to hold
      // it. Attach it now so the approved reference travels into production.
      if (designBoard.boardId && designBoard.approved) {
        try {
          await api.saveDesignBoardToOrder(designBoard.boardId, order.order_id);
        } catch (err) {
          // Say so. This used to console.error only, so an order whose design
          // failed to attach still produced the green confirmation screen and
          // went to the floor carrying no design at all. The order itself is
          // already saved and is not worth rolling back for this, so tell the
          // owner what is missing and let them re-attach.
          console.error("Could not attach the design board to the order", err);
          alert(
            `Order ${order.order_id} was created, but the approved design could not be `
            + `attached to it (${err.message}). Open the order and set the design before `
            + `it goes to the tailor.`);
        }
      }
      setConfirmedOrder(order);
      setView('confirmed');
    } catch (err) {
      console.error(err);
      alert("Failed to submit order.");
    }
  };

  // One click, one call.
  //
  // Every wizard CTA is an async handler that talks to the API, and none of them
  // guarded against being entered twice. A double-click on Next ran saveStep1
  // twice, which is two createCustomer POSTs and two customer records for one
  // person. The ref is what does the work: a second click in the same tick sees
  // it synchronously, where a state flag would not have re-rendered yet. The
  // state is only so the button can show it is busy.
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

  const performNext = async () => {
    try {
      // Checked on every step, not only the first. 'Reorder Style' drops the
      // owner straight into step 3 without ever setting garmentJobs, so the
      // step-1 guard was skipped entirely and the wizard happily booked an
      // order with no dress on it -- saveGarmentJobs iterated an empty array
      // and nobody found out until production. Guarding at the point of
      // submission is the choke point; no entry point can route around it.
      if (garmentJobs.length === 0) {
        alert("Please choose at least one garment for this order.");
        if (currentStep !== 1) setCurrentStep(1);
        return;
      }
      if (currentStep === 1) {
        await saveStep1();
        setCurrentStep(2);
      } else if (currentStep === 2) {
        // The server validates this again on save; failing here first means the
        // staff member sees which field is wrong instead of a rejected order.
        if (!validateGarments()) {
          alert("Some garment details are missing or invalid — see the highlighted fields.");
          return;
        }
        await saveStep2();
        setCurrentStep(3);
      } else if (currentStep === 3) {
        await saveStep3();
        setCurrentStep(4);
      } else if (currentStep === 4) {
        if (fabricTab === 'boutique' && !selectedFabric) {
          alert("Please select a fabric from the catalog or upload your own fabric.");
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

  const getSubtotal = () => {
    const base = parseFloat(quotePrices.base || 0);
    const fabricPrice = parseFloat(quotePrices.fabric || 0);
    const embroidery = parseFloat(quotePrices.embroidery || 0);
    const customization = parseFloat(quotePrices.customization || 0);
    const tailoring = parseFloat(quotePrices.tailoring || 0);
    const packaging = parseFloat(quotePrices.packaging || 0);
    return base + fabricPrice + embroidery + customization + tailoring + packaging;
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

  // Opens the stage review panel for a given order and stage.
  const openStageReview = (order, stage) => {
    setActiveReviewStage(stage.stage_name);
    setActiveReviewOrder(order);
    setSelectedStageObj(stage);
    setStageReviewComments(stage.comments || '');
    setStageReviewImage(null);
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
        <div className="auth-page" style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#faf9f6', padding: '40px 20px' }}>
          
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

          <div className="auth-card" style={{ maxWidth: '420px', width: '100%', background: '#fff', border: '1px solid #eaecef', borderRadius: '16px', padding: '40px', boxShadow: '0 8px 30px rgba(0,0,0,0.02)' }}>
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
                <label className="remember-me-checkbox" style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                  <input type="checkbox" defaultChecked style={{ accentColor: '#b07c40' }} />
                  Remember me
                </label>
                {/* No reset flow exists anywhere in the product -- no view, no
                    url, no serializer -- so this promised the only recovery
                    path a locked-out owner has and delivered nothing. Pointing
                    them at the boutique instead is honest; the real flow is a
                    feature, not a fix. */}
                <span className="forgot-password-link" style={{ color: 'var(--text-secondary)', fontWeight: 500, whiteSpace: 'nowrap' }}>
                  Password help? Ask your admin
                </span>
              </div>

              <button type="submit" className="btn-primary" style={{ justifyContent: 'center', padding: '14px', borderRadius: '8px', fontWeight: 600, fontSize: '14px' }}>
                Login to Workspace
              </button>
            </form>

            <div className="divider-container" style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '11px', color: 'var(--text-muted)', margin: '24px 0', textTransform: 'uppercase', letterSpacing: '1px' }}>
              <div style={{ flex: 1, height: '1px', background: '#eaecef' }}></div>
              OR CONTINUE WITH
              <div style={{ flex: 1, height: '1px', background: '#eaecef' }}></div>
            </div>

            <div className="social-auth-buttons" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <button className="social-btn" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #eaecef', background: '#fff', fontSize: '13px', cursor: 'pointer' }}>
                <Compass size={16} />
                Continue with Google
              </button>
              <button className="social-btn" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #eaecef', background: '#fff', fontSize: '13px', cursor: 'pointer' }}>
                <User size={16} />
                Continue with Apple
              </button>
            </div>

            <div className="auth-card-footer" style={{ borderTop: '1px solid #eaecef', marginTop: '32px', paddingTop: '20px', textAlign: 'center', fontSize: '13.5px', color: 'var(--text-secondary)' }}>
              Don't have a boutique account? <a href="#" style={{ color: 'var(--accent-text, #b07c40)', fontWeight: 600, textDecoration: 'none' }} onClick={() => { setSignupStep(1); setView('signup'); }}>Signup</a>
            </div>
          </div>
        </div>
      )}

      {/* 3. SIGN UP SCREEN (Image 3) */}
      {view === 'signup' && (
        <div className="auth-page" style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#faf9f6', padding: '40px 20px' }}>
          
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
            {[
              { step: 1, label: 'Account' },
              { step: 2, label: 'Verify' },
              { step: 3, label: 'Profile' },
              { step: 4, label: 'Preferences' },
              { step: 5, label: 'Complete' }
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
                <h2 className="auth-title">Verify Mobile Number</h2>
                <p className="auth-subtitle">We have sent a 6-digit OTP code to +91 {signupForm.mobile_number}</p>
                
                <div className="auth-form">
                  <div className="form-group">
                    <label className="form-label">Verification Code (OTP)</label>
                    <input 
                      type="text" 
                      maxLength="6"
                      placeholder="Enter 6-digit code"
                      className="form-control"
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value)}
                      style={{ textAlign: 'center', letterSpacing: '8px', fontSize: '20px' }}
                    />
                  </div>

                  <button className="btn-primary" style={{ justifyContent: 'center' }} onClick={handleVerifyOTP}>
                    Verify OTP
                  </button>
                  <button className="btn-secondary" style={{ justifyContent: 'center' }} onClick={() => setSignupStep(1)}>
                    Back
                  </button>
                </div>
              </>
            )}

            {signupStep === 3 && (
              <>
                <h2 className="auth-title">Complete Profile</h2>
                <p className="auth-subtitle">Tell us about your boutique role and communication channel.</p>
                
                <div className="auth-form">
                  <div className="form-group">
                    <label className="form-label">Occupation / Role</label>
                    <input 
                      type="text" 
                      placeholder="e.g. Master Stylist, Atelier Director"
                      className="form-control"
                      value={profileOccupation}
                      onChange={(e) => setProfileOccupation(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Preferred Communication channel</label>
                    <select 
                      className="form-control"
                      value={profileComm}
                      onChange={(e) => setProfileComm(e.target.value)}
                    >
                      <option value="WhatsApp">WhatsApp</option>
                      <option value="Call">Phone Call</option>
                      <option value="Email">Email</option>
                    </select>
                  </div>

                  <button className="btn-primary" style={{ justifyContent: 'center' }} onClick={handleProfileSubmit}>
                    Next: Customizer Prefs
                  </button>
                </div>
              </>
            )}

            {signupStep === 4 && (
              <>
                <h2 className="auth-title">Design Style Preferences</h2>
                <p className="auth-subtitle">Select style tags that correspond to your boutique specialization.</p>
                
                <div className="auth-form">
                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', margin: '16px 0' }}>
                    {['Bridal Lehenga', 'Embroidery Gowns', 'Mens Sherwani', 'Premium Silk Sarees', 'Designer Kurta Sets', 'Western Suits'].map(tag => (
                      <span 
                        key={tag} 
                        style={{ 
                          padding: '8px 16px', 
                          borderRadius: '99px', 
                          border: '1px solid #b07c40', 
                          backgroundColor: '#fcf6ee',
                          color: '#b07c40',
                          fontSize: '12px',
                          fontWeight: '600'
                        }}
                      >
                        {tag}
                      </span>
                    ))}
                  </div>

                  <button className="btn-primary" style={{ justifyContent: 'center' }} onClick={handleCompleteRegistration}>
                    Submit Registration
                  </button>
                </div>
              </>
            )}

            {signupStep === 5 && (
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
            title={dashboardTab === 'overview' ? 'Dashboard' : dashboardTab.charAt(0).toUpperCase() + dashboardTab.slice(1)}
            currentUser={currentUser}
            notificationsCount={notifications.filter(n => !n.is_read).length}
            onOpenMenu={() => setMobileNavOpen(!mobileNavOpen)}
            onOpenNotifications={() => {
              setShowNotificationsDrawer(true);
              api.markNotificationsAsRead(currentUser.role || 'Owner', currentUser.email)
                .then(() => fetchNotifications());
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
                    .then(() => fetchNotifications());
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
                    .then(() => fetchNotifications());
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
                <span>Inbox Alerts</span>
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
                  <a className={`portal-menu-item ${dashboardTab === 'overview' ? 'active' : ''}`} onClick={() => { setDashboardTab('overview'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Users size={16} /> Dashboard</a>
                  <a className={`portal-menu-item ${dashboardTab === 'orders' ? 'active' : ''}`} onClick={() => { setDashboardTab('orders'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><ShoppingBag size={16} /> Manage Orders</a>
                  <a className={`portal-menu-item ${dashboardTab === 'customers' ? 'active' : ''}`} onClick={() => { setDashboardTab('customers'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Users size={16} /> Customers</a>
                  <a className={`portal-menu-item ${dashboardTab === 'invoices' ? 'active' : ''}`} onClick={() => { setDashboardTab('invoices'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><FileText size={16} /> Invoices</a>
                  <a className={`portal-menu-item ${dashboardTab === 'analytics' ? 'active' : ''}`} onClick={() => { setDashboardTab('analytics'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><BarChart2 size={16} /> Analytics</a>
                  <a className={`portal-menu-item ${dashboardTab === 'fabrics' ? 'active' : ''}`} onClick={() => { setDashboardTab('fabrics'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Compass size={16} /> Manage Fabrics</a>
                  <a className={`portal-menu-item ${dashboardTab === 'inventory' ? 'active' : ''}`} onClick={() => { setDashboardTab('inventory'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Package size={16} /> Inventory</a>
                  <a className={`portal-menu-item ${dashboardTab === 'tailors' ? 'active' : ''}`} onClick={() => { setDashboardTab('tailors'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Scissors size={16} /> Manage Tailors</a>
                  <a className={`portal-menu-item ${dashboardTab === 'designs' ? 'active' : ''}`} onClick={() => { setDashboardTab('designs'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Sparkles size={16} /> Manage Designs</a>
                </>
              ) : currentUser.role === 'Master' ? (
                <>
                  <a className={`portal-menu-item ${dashboardTab === 'assignments' ? 'active' : ''}`} onClick={() => { setDashboardTab('assignments'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Scissors size={16} /> My Assignments</a>
                  <a className={`portal-menu-item ${dashboardTab === 'orders' ? 'active' : ''}`} onClick={() => { setDashboardTab('orders'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><ShoppingBag size={16} /> Manage Orders</a>
                  <a className={`portal-menu-item ${dashboardTab === 'customers' ? 'active' : ''}`} onClick={() => { setDashboardTab('customers'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Users size={16} /> Customers</a>
                </>
              ) : currentUser.role === 'Designer' ? (
                // A designer's account exists for exactly one thing: their own
                // uploads and portfolio. No customer, order or financial nav
                // item is offered, matching the module's permission matrix --
                // see docs/design-management.md section 4 for the caveat that
                // this is a UI restriction, not an API-level one.
                <a className={`portal-menu-item ${dashboardTab === 'designs' ? 'active' : ''}`} onClick={() => { setDashboardTab('designs'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Sparkles size={16} /> Design Studio</a>
              ) : (
                <a className={`portal-menu-item ${dashboardTab === 'assignments' ? 'active' : ''}`} onClick={() => { setDashboardTab('assignments'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><Scissors size={16} /> My Assignments</a>
              )}
              <a className={`portal-menu-item ${dashboardTab === 'account' ? 'active' : ''}`} onClick={() => { setDashboardTab('account'); setSelectedDirectoryCustomer(null); setMobileNavOpen(false); }}><User size={16} /> My Account</a>
              <a className="portal-menu-item" onClick={() => { handleLogout(); setMobileNavOpen(false); }}><LogOut size={16} /> Logout</a>
            </nav>

            <div className="portal-sidebar-footer">
              <div className="portal-sidebar-help">
                <h4 style={{ fontSize: '12px', fontWeight: 700 }}>Need Help?</h4>
                <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Our style concierge is here to assist you.</p>
                <button 
                  className="whatsapp-btn" 
                  style={{ width: '100%', padding: '6px', fontSize: '11px' }}
                  onClick={() => window.open('https://wa.me/919876543210')}
                >
                  <MessageSquare size={12} />
                  Chat Now
                </button>
              </div>
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
                        Logged in as {currentUser.first_name} ({currentUser.role}). View and manage your active orders.
                      </p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(currentUser.first_name)}`} alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
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
                        currentUser.role === 'Master' ? o.master === currentUser.tailor_id : o.tailor === currentUser.tailor_id
                      ).length === 0 ? (
                        <p style={{ color: 'var(--text-muted)', padding: '16px 0', textAlign: 'center', fontSize: '13px' }}>
                          No active orders are assigned to you at the moment.
                        </p>
                      ) : (
                        ordersList.filter(o => 
                          currentUser.role === 'Master' ? o.master === currentUser.tailor_id : o.tailor === currentUser.tailor_id
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
                                  Client: {order.customer_name} | Est. Delivery: {order.estimated_delivery ? new Date(order.estimated_delivery).toLocaleDateString() : 'TBD'}
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
                              <div className="assignment-card-sub-info" style={{ borderBottom: (currentUser.role !== 'Tailor' || order.customer_measurements) ? '1px solid var(--border-color)' : 'none', paddingBottom: '10px', fontSize: '13px' }}>
                                {currentUser.role !== 'Tailor' && <div>Total Value: <span style={{ fontWeight: 600 }}>₹{parseFloat(order.total_amount).toLocaleString()}</span></div>}
                                <div>Assigned Supervising Master: <span style={{ fontWeight: 600, color: 'var(--accent-color, #d4af37)' }}>{order.master_name || 'Unassigned'}</span></div>
                                <div>Assigned Stitching Tailor: <span style={{ fontWeight: 600 }}>{order.tailor_name || 'Unassigned'}</span></div>
                              </div>

                              {/* Client specifications and measurements passed to Tailor flow */}
                              {order.customer_measurements && (
                                <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                                  <div className="assignment-card-blueprint-header" style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                    <span>
                                      Dress / Garment Type: <span style={{ color: 'var(--accent-text, #b07c40)' }}>{order.customer_garment_type || 'Custom Item'}</span>
                                      {(() => {
                                        const parts = order.customer_measurements.additional_measurements?.stitch_parts || [];
                                        return parts.length > 0 && ` (${parts.join(', ')})`;
                                      })()}
                                    </span>
                                    <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)' }}>📍 Sizing Blueprint Passed From Master</span>
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
                            {(currentUser.role === 'Master' || currentUser.role === 'Owner' || !currentUser.role) && (
                              <div>
                                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '2px' }}>
                                  Production Stages — select a stage to update
                                </div>
                                <StageTimeline
                                  stages={order.stages}
                                  onSelectStage={(stage) => openStageReview(order, stage)}
                                />
                              </div>
                            )}

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
                                              await api.updateOrder(order.id, { master_verification: updatedVerification });
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
                                        <a href={order.completed_garment_image} target="_blank" rel="noreferrer" style={{ fontSize: '11px', color: 'var(--accent-color, #d4af37)', textDecoration: 'underline' }}>View Image</a>
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
                        Welcome back, {currentUser.first_name}! 👋
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Your custom creation journey starts here.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <button className="btn-primary" onClick={() => setView('order-selector')}>
                      <Sparkles size={16} />
                      New Custom Order
                    </button>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
                    </div>
                  </div>
                </header>

                {/* Quick Action Grid */}
                <section className="quick-action-button-grid">
                  <div className="quick-action-item" onClick={() => setView('order-selector')}>
                    <div className="quick-action-icon-box"><ShoppingBag size={18} /></div>
                    <h4>New Order</h4>
                    <p>Start custom order</p>
                  </div>
                  <div className="quick-action-item" onClick={() => setDashboardTab('tailors')}>
                    <div className="quick-action-icon-box"><Scissors size={18} /></div>
                    <h4>Manage Staff</h4>
                    <p>Tailors & status</p>
                  </div>
                  <div className="quick-action-item" onClick={() => setDashboardTab('designs')}>
                    <div className="quick-action-icon-box"><Heart size={18} /></div>
                    <h4>Design Catalog</h4>
                    <p>Style collections</p>
                  </div>
                  <div className="quick-action-item" onClick={() => setDashboardTab('fabrics')}>
                    <div className="quick-action-icon-box"><Compass size={18} /></div>
                    <h4>Fabric Library</h4>
                    <p>Explore fabrics</p>
                  </div>
                  {/* This tile was the one of five with no onClick at all --
                      it looked identical to its four working siblings and did
                      nothing when pressed. Booking now opens a real
                      appointment against apps/scheduling. */}
                  <div className="quick-action-item" onClick={() => setShowAppointmentModal(true)}>
                    <div className="quick-action-icon-box"><Calendar size={18} /></div>
                    <h4>Book Appointment</h4>
                    <p>Consult with stylist</p>
                  </div>
                </section>

                {/* Row Layout: Orders & Progress Tracker */}
                <div className="dashboard-row-layout">
                  {/* Active Orders List */}
                  <div className="orders-list-panel">
                    <div className="panel-header-row">
                      <h3 style={{ fontSize: '16px', fontWeight: 600 }}>My Orders</h3>
                      <a className="view-all-link" style={{ cursor: 'pointer' }} onClick={() => setDashboardTab('orders')}>VIEW ALL ORDERS →</a>
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
                              <div className="order-row-id">Order ID: {order.order_id}</div>
                              <div className="order-row-name">{order.customer_name} • {order.order_status}</div>
                              <div className="order-row-fabric">Tailor: {order.tailor_name || 'Unassigned'}</div>
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
                                {order.order_status || 'In Progress'}
                              </span>
                              <span className="order-row-date">Est. {new Date(order.estimated_delivery).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Order Live Tracker Sidebar */}
                  <div className="order-detail-progress-card">
                    <div className="panel-header-row">
                      <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Order Progress</h3>
                      <a className="view-all-link" style={{ cursor: 'pointer' }} onClick={() => setDashboardTab('orders')}>VIEW ALL</a>
                    </div>

                    {selectedDashboardOrder ? (
                      <>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <div style={{ fontSize: '13px', fontWeight: 600 }}>{selectedDashboardOrder.customer_name}</div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Order ID: {selectedDashboardOrder.order_id}</div>
                        </div>

                        <div style={{ marginTop: '12px', marginBottom: '16px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontWeight: 600, marginBottom: '4px' }}>
                            <span>PRODUCTION PROGRESS</span>
                            <span>{(() => {
                              const stages = selectedDashboardOrder.stages || [];
                              const completed = stages.filter(s => s.status === 'COMPLETED').length;
                              const pct = stages.length > 0 ? Math.round((completed / stages.length) * 100) : 0;
                              return `${pct}% (${completed}/${stages.length} Stages)`;
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
                                        <span style={{ fontSize: '10px', color: 'var(--text-muted)', flexShrink: 0 }}>Assign:</span>
                                        <select
                                          className="form-control"
                                          style={{ fontSize: '10px', padding: '2px 4px', height: 'auto' }}
                                          value={stage.assigned_to || ''}
                                          disabled={assigningStageKey === stage.stage_key}
                                          onChange={e => handleAssignStage(
                                            selectedDashboardOrder.id, stage.stage_key, e.target.value
                                          )}
                                        >
                                          <option value="">Unassigned</option>
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
                          <div style={{ fontWeight: 600, marginBottom: '4px' }}>Delivery Method: {selectedDashboardOrder.delivery_method}</div>
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
                              <Scissors size={12} style={{ color: 'var(--accent-color, #d4af37)' }} />
                              <span>Tailor Completion Notes</span>
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
                            <span style={{ fontSize: '12px', fontWeight: 600 }}>Update Status:</span>
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
                                <option key={status} value={status} style={{ background: '#222', color: '#fff' }}>{status}</option>
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
                              Advance to Next Stage
                            </button>
                          )}
                        </div>
                      </>
                    ) : (
                      <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '12px' }}>
                        Select an order on the left to see progress details.
                      </div>
                    )}
                  </div>
                </div>

                {/* Upcoming Appointments & Style Inspiration Row */}
                <div className="dashboard-row-layout">
                  <div>
                    <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Upcoming Appointments</h3>
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
                          No appointments booked.
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
                                {APPOINTMENT_TYPE_LABELS[appt.appointment_type] || 'Appointment'}
                              </span>
                              <span className="appt-sub">
                                {appt.customer_detail
                                  ? `${appt.customer_detail.first_name} ${appt.customer_detail.last_name}`
                                  : 'Client'}
                                {appt.assigned_staff_detail ? ` · with ${appt.assigned_staff_detail.name}` : ''}
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

                  <div>
                    <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Style Inspiration</h3>
                    <div className="inspiration-grid-row">
                      <div className="inspiration-circle-avatar">
                        <img src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100" alt="Insp1" />
                      </div>
                      <div className="inspiration-circle-avatar">
                        <img src="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100" alt="Insp2" />
                      </div>
                      <div className="inspiration-circle-avatar">
                        <img src="https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100" alt="Insp3" />
                      </div>
                    </div>
                  </div>
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
                        Manage Fabric Library
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Configure, add, or edit boutique catalog fabrics.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <button className="btn-primary" onClick={() => {
                      setEditingFabric(null);
                      setFabricForm({ name: '', material: '', color: '', price_per_meter: '', image_url: '', is_available: true });
                      setShowFabricModal(true);
                    }}>
                      <Plus size={16} />
                      Add New Fabric
                    </button>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
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
                            <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--accent-color, #d4af37)', marginTop: '4px' }}>
                              ₹{parseFloat(fabric.price_per_meter).toLocaleString('en-IN')}/mtr
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
                        Manage Tailoring Staff
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Add, configure, or review in-house custom tailors.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <button className="btn-primary" onClick={() => {
                      setEditingTailor(null);
                      setTailorForm({ name: '', email: '', specialty: '', rating: 5.0, status: 'Available', role: 'Tailor' });
                      setShowTailorModal(true);
                    }}>
                      <Plus size={16} />
                      Add New Tailor
                    </button>
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
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
                        <Scissors size={20} style={{ color: 'var(--accent-color, #d4af37)' }} />
                        <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>Master Tailors (Cutting & Supervision)</h3>
                      </div>
                      
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {tailors.filter(t => t.role === 'Master').length === 0 ? (
                          <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>No Master Tailors registered yet.</p>
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
                                  {tailor.status}
                                </span>
                                <button className="btn-secondary" style={{ padding: '6px 10px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }} onClick={() => {
                                  if (!tailor.email) {
                                    alert("Please edit this tailor's profile to add their email address first.");
                                    return;
                                  }
                                  setShareCredsTailor(tailor);
                                }}>
                                  <Lock size={12} /> Share
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
                                }}>Edit</button>
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
                        <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>Stitching Tailors (Assembly & Detailing)</h3>
                      </div>
                      
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {tailors.filter(t => t.role !== 'Master').length === 0 ? (
                          <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>No Stitching Tailors registered yet.</p>
                        ) : (
                          tailors.filter(t => t.role !== 'Master').map(tailor => (
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
                                  {tailor.status}
                                </span>
                                <button className="btn-secondary" style={{ padding: '6px 10px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }} onClick={() => {
                                  if (!tailor.email) {
                                    alert("Please edit this tailor's profile to add their email address first.");
                                    return;
                                  }
                                  setShareCredsTailor(tailor);
                                }}>
                                  <Lock size={12} /> Share
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
                                }}>Edit</button>
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
                      <Sparkles size={20} style={{ color: 'var(--accent-color, #d4af37)' }} />
                      <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>Workflow Assignment & Supervision Control</h3>
                    </div>
                    
                    <div style={{ overflowX: 'auto' }}>
                      <table className="portal-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ textAlign: 'left', borderBottom: '1.5px solid var(--border-color)' }}>
                            <th style={{ padding: '12px 16px', fontSize: '13px', fontWeight: 600 }}>Order / Client</th>
                            <th style={{ padding: '12px 16px', fontSize: '13px', fontWeight: 600 }}>Status</th>
                            <th style={{ padding: '12px 16px', fontSize: '13px', fontWeight: 600 }}>Supervising Master</th>
                            <th style={{ padding: '12px 16px', fontSize: '13px', fontWeight: 600 }}>Stitching Tailor</th>
                          </tr>
                        </thead>
                        <tbody>
                          {ordersList.filter(o => ['Received', 'Confirmed', 'Stylist Review', 'Design & Creation', 'Quality Check', 'Ready for Dispatch', 'Shipped'].includes(o.order_status)).length === 0 ? (
                            <tr>
                              <td colSpan="4" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                                No active orders in creation phase.
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
                                    {order.order_status}
                                  </span>
                                </td>
                                <td style={{ padding: '16px' }}>
                                  <select 
                                    className="form-control"
                                    style={{ fontSize: '13px', padding: '6px 12px', width: '200px' }}
                                    value={order.master || ''}
                                    onChange={(e) => handleAssignWorkflow(order.id, { master: e.target.value || null })}
                                  >
                                    <option value="">Unassigned</option>
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
                                    <option value="">Unassigned</option>
                                    {tailors.filter(t => t.role !== 'Master').map(s => (
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

            {/* 4. MANAGE DESIGNS TAB */}
            {dashboardTab === 'designs' && (
              <>
                <header className="portal-header">
                  <div className="portal-header-left">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
                        Manage Design Collections
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Add, edit, or remove catalog designs and AI suggestions.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    {/* This posts through the catalogue's own endpoint, which
                        (unlike DesignAssetViewSet) has no per-design ownership
                        check -- so it stays Owner-only rather than opened to a
                        Designer the way the library's own upload flow below
                        already is. */}
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
                        Add New Design
                      </button>
                    )}
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
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
                        Atelier Orders Registry
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                        Search, filter, and track all custom creations and dispatch logistics.
                      </p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <button className="btn-primary" onClick={handleStartNewCustomer}>
                      <Plus size={16} /> New Custom Order
                    </button>
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
                    {/* Filter Tabs */}
                    <div style={{ display: 'flex', gap: '8px' }}>
                      {['All', 'Active', 'Shipped', 'Delivered'].map(statusTab => (
                        <button 
                          key={statusTab}
                          onClick={() => setOrdersFilterTab(statusTab)}
                          className={ordersFilterTab === statusTab ? 'btn-primary' : 'btn-secondary'}
                          style={{ padding: '6px 16px', fontSize: '13px' }}
                        >
                          {statusTab}
                        </button>
                      ))}
                    </div>

                    {/* Search Input */}
                    <div className="search-bar-container" style={{ width: '300px', margin: 0 }}>
                      <Search className="search-icon" size={16} />
                      <input 
                        type="text" 
                        placeholder="Search by Order ID or Client..."
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
                            No orders found matching the criteria.
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
                                  {order.order_status}
                                </span>
                              </div>
                              <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                                Client: <strong>{order.customer_name}</strong> | Created: {new Date(order.order_date).toLocaleDateString()}
                              </div>
                              {(() => {
                                const v = order.master_verification || {};
                                const total = 6 + (order.customer_garment_type === 'Saree' ? 1 : 0);
                                const checked = Object.values(v).filter(Boolean).length;
                                if (checked > 0) {
                                  return (
                                    <div style={{ fontSize: '11px', color: 'var(--accent-text, #b07c40)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'rgba(212,175,55,0.08)', padding: '2px 8px', borderRadius: '4px', marginTop: '4px' }}>
                                      <span>👑 Master Verified: {checked}/{total} items ({Math.round((checked/total)*100)}%)</span>
                                    </div>
                                  );
                                }
                                return null;
                              })()}
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                              <span style={{ fontSize: '13px', fontWeight: 600 }}>Update Status:</span>
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
                                  <option key={status} value={status}>{status}</option>
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
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>Supervising Master</span>
                              <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px', color: 'var(--accent-color, #d4af37)' }}>{order.master_name || 'Unassigned'}</div>
                            </div>
                            <div>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>Stitching Tailor</span>
                              <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px' }}>{order.tailor_name || 'Unassigned'}</div>
                            </div>
                            <div>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>Total Value</span>
                              <div style={{ fontSize: '14px', fontWeight: 700, marginTop: '2px', color: 'var(--text-primary)' }}>₹{parseFloat(order.total_amount).toLocaleString()}</div>
                            </div>
                            <div>
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>Est. Delivery</span>
                              <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px' }}>{order.estimated_delivery ? new Date(order.estimated_delivery).toLocaleDateString() : 'TBD'}</div>
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
                                            await api.updateOrder(order.id, { master_verification: updatedVerification });
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
                              Delivery Method: {order.delivery_method}
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
                                <Scissors size={14} style={{ color: 'var(--accent-color, #d4af37)' }} />
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
                        Customer Directory
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>View client profiles, style files, and body measurements.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <div className="search-input-wrapper" style={{ margin: 0 }}>
                      <Search size={18} />
                      <input 
                        type="text" 
                        placeholder="Search customers..." 
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
                      <span>Hi, {currentUser.first_name}</span>
                    </div>
                  </div>
                </header>

                {/* Customer Type Filters */}
                <div style={{ display: 'flex', gap: '12px', marginTop: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
                  {['All', 'Women', 'Men', 'Kids'].map(type => (
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
                      {type}
                    </button>
                  ))}
                </div>

                <div className="customers-list-container" style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {loading && customersList.length === 0 ? (
                    <div style={{ padding: '48px', textAlign: 'center', background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                      <span style={{ color: 'var(--text-muted)' }}>Loading customer directory…</span>
                    </div>
                  ) : loadErrors.includes('customers') ? (
                    <div style={{ padding: '48px', textAlign: 'center', background: 'rgba(127,29,29,0.15)', borderRadius: '12px', border: '1px solid rgba(220,38,38,0.3)' }}>
                      <div style={{ color: '#fca5a5', marginBottom: '12px' }}>Could not load the customer directory.</div>
                      <button type="button" className="btn-secondary" onClick={() => fetchDashboardAndConfig()}>Retry</button>
                    </div>
                  ) : directoryCustomers.length === 0 ? (
                    <div style={{ padding: '48px', textAlign: 'center', background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                      <span style={{ color: 'var(--text-muted)' }}>No customers found matching current filters</span>
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
                            <div>📞 {cust.mobile_number}</div>
                            {cust.email_address && <div>✉️ {cust.email_address}</div>}
                            {cust.address && <div>📍 {cust.address}, {cust.city_region}</div>}
                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>Registered: {new Date(cust.created_at).toLocaleDateString()}</div>
                          </div>
                        </div>

                        {/* Measurements */}
                        <div style={{ borderLeft: '1px solid rgba(255,255,255,0.05)', paddingLeft: '24px' }}>
                          <h5 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Body Measurements</h5>
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
                          <h5 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Bespoke Profile</h5>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', fontSize: '12px' }}>
                            <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Garment: {cust.garment_type}{cust.measurements?.additional_measurements?.stitch_parts?.length > 0 ? ` (${cust.measurements.additional_measurements.stitch_parts.join(', ')})` : ''}</span>
                            {cust.neckline_style && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Neck: {cust.neckline_style}</span>}
                            {cust.sleeve_style && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Sleeve: {cust.sleeve_style}</span>}
                            {cust.silhouette && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Silhouette: {cust.silhouette}</span>}
                            {cust.occasion && <span style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 8px', borderRadius: '4px' }}>Occasion: {cust.occasion}</span>}
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
                            <Sparkles size={16} style={{ color: 'var(--accent-color, #d4af37)' }} />
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
                            {expandedDna[cust.id] ? 'Hide Style DNA' : 'View Style DNA'}
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
                                      <td style={{ padding: '12px 0', color: 'var(--accent-color, #d4af37)', fontWeight: 600 }}>"{cust.style_dna?.next_action}"</td>
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
                      color: 'var(--accent-color, #d4af37)',
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
                        borderColor: 'var(--accent-color, #d4af37)',
                        color: 'var(--accent-color, #d4af37)',
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
                      <span>📞 {selectedDirectoryCustomer.mobile_number}</span>
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
                              border: `1px solid ${isOpen ? 'var(--accent-color, #d4af37)' : 'var(--border-color)'}`,
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
                                    Date: {new Date(order.order_date).toLocaleDateString()} | Tailor: {order.tailor_name || 'Not assigned'}
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
                                    <div style={{ fontWeight: 700, color: 'var(--accent-color, #d4af37)', fontSize: '14px' }}>₹{parseFloat(order.total_amount).toLocaleString()}</div>
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
                                              {new Date(stage.completed_at).toLocaleDateString()}
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
                                      <span>Expected: <strong style={{ color: 'var(--text-primary)' }}>{new Date(order.estimated_delivery).toLocaleDateString()}</strong></span>
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
                                      setQuotePrices({
                                        base: order.base_price,
                                        fabric: order.fabric_price,
                                        embroidery: order.embroidery_price,
                                        customization: order.customization_price,
                                        tailoring: order.tailoring_charges,
                                        packaging: order.packaging_handling
                                      });
                                      setCurrentStep(3);
                                      setView('wizard');
                                    }}
                                    style={{
                                      background: 'rgba(212, 175, 55, 0.1)',
                                      border: '1px solid rgba(212, 175, 55, 0.3)',
                                      color: 'var(--accent-color, #d4af37)',
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
                        Invoices & Billing
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Manage invoices, verify billing payments, and print receipts.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
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
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>Total Collected Revenue</span>
                        <div style={{ fontSize: '24px', fontWeight: 700, color: '#107c41', marginTop: '8px' }}>₹{paidTotal.toLocaleString('en-IN')}</div>
                      </div>
                      <div className="stat-card" style={{ padding: '20px', border: '1px solid var(--border-color)' }}>
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>Outstanding Balance</span>
                        <div style={{ fontSize: '24px', fontWeight: 700, color: '#d4af37', marginTop: '8px' }}>₹{pendingTotal.toLocaleString('en-IN')}</div>
                      </div>
                      <div className="stat-card" style={{ padding: '20px', border: '1px solid var(--border-color)' }}>
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>Total Invoiced Volume</span>
                        <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '8px' }}>₹{grandTotal.toLocaleString('en-IN')}</div>
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
                        {option}
                      </button>
                    ))}
                  </div>

                  <div className="search-bar-container" style={{ width: '300px', margin: 0 }}>
                    <Search className="search-icon" size={16} />
                    <input 
                      type="text" 
                      placeholder="Search Invoice ID or Client..."
                      className="search-input"
                      value={invoiceSearch}
                      onChange={(e) => setInvoiceSearch(e.target.value)}
                    />
                  </div>
                </div>

                <div className="invoices-content" style={{ marginTop: '24px' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', background: 'var(--surface-color)', borderRadius: '12px', border: '1px solid var(--border-color)', overflow: 'hidden' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border-color)', background: 'rgba(0,0,0,0.015)' }}>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Invoice ID</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Billing Client</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Date</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Total Price</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Advance Paid</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Total Paid</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Balance Due</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Payment Status</th>
                        <th style={{ padding: '16px', fontSize: '13px', fontWeight: 600 }}>Action</th>
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
                              <td colSpan="11" style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>No invoices matching the criteria.</td>
                            </tr>
                          );
                        }

                        return filtered.map(order => (
                          <tr key={order.id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '14px' }}>
                            <td style={{ padding: '16px', fontFamily: 'monospace', fontWeight: 600 }}>{order.order_id}</td>
                            <td style={{ padding: '16px' }}>{order.customer_name}</td>
                            <td style={{ padding: '16px', color: 'var(--text-secondary)' }}>{new Date(order.order_date).toLocaleDateString()}</td>
                            <td style={{ padding: '16px', fontWeight: 600 }}>₹{parseFloat(order.total_amount).toLocaleString('en-IN')}</td>
                            <td style={{ padding: '16px', color: 'var(--text-secondary)' }}>₹{parseFloat(order.advance_paid || 0).toLocaleString('en-IN')}</td>
                            <td style={{ padding: '16px', color: '#107c41', fontWeight: 600 }}>₹{parseFloat(order.amount_paid || 0).toLocaleString('en-IN')}</td>
                            <td style={{ padding: '16px', color: '#ff4d4d', fontWeight: 600 }}>₹{Math.max(0, parseFloat(order.total_amount) - parseFloat(order.amount_paid || 0)).toLocaleString('en-IN')}</td>
                            <td style={{ padding: '16px' }}>
                              <select 
                                value={order.payment_status}
                                onChange={async (e) => {
                                  try {
                                    await api.updateOrder(order.id, { payment_status: e.target.value });
                                    fetchDashboardAndConfig();
                                  } catch (err) {
                                    alert("Failed to update payment status: " + err.message);
                                  }
                                }}
                                className="form-control"
                                style={{ padding: '4px 8px', fontSize: '12px', width: '130px', margin: 0 }}
                              >
                                <option value="Pending">Pending</option>
                                <option value="Partially Paid">Partially Paid</option>
                                <option value="Paid">Paid</option>
                              </select>
                            </td>
                            <td style={{ padding: '16px' }}>
                              <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => {
                                setConfirmedOrder(order);
                                setShowInvoiceModal(true);
                              }}>
                                <FileText size={12} /> View Invoice
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

              const garmentDist = {};
              customersList.forEach(c => {
                if (c.garment_type) garmentDist[c.garment_type] = (garmentDist[c.garment_type] || 0) + 1;
              });

              const necklineDist = {};
              const sleeveDist = {};
              customersList.forEach(c => {
                if (c.neckline_style) necklineDist[c.neckline_style] = (necklineDist[c.neckline_style] || 0) + 1;
                if (c.sleeve_style) sleeveDist[c.sleeve_style] = (sleeveDist[c.sleeve_style] || 0) + 1;
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
                          Business Analytics & Trends
                        </h1>
                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Summary of revenues, style preferences, and operations workload.</p>
                      </div>
                    </div>
                    <div className="portal-header-right">
                      <div className="user-profile-widget">
                        <div className="user-avatar-circle">
                          <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                        </div>
                        <span>Hi, {currentUser.first_name}</span>
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
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Collected Revenue</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: 'var(--accent-color, #d4af37)' }}>
                        ₹{paidRevenue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>From paid customer orders</span>
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
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Pending Invoices</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: '#ffc107' }}>
                        ₹{pendingBill.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Awaiting full or partial payment</span>
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
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Average Ticket Size</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: '#4a90e2' }}>
                        ₹{aov.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Per bespoke order</span>
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
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Client Base</span>
                      <span style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-serif)', color: '#2ec4b6' }}>
                        {customersList.length} Clients
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Total boutique directory profiles</span>
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
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Popular Garment Types</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          {topGarmentsList.map(([garment, count], idx) => {
                            const pct = Math.round((count / customersList.length) * 100) || 0;
                            return (
                              <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                <div style={{ display: 'flex', justifycontent: 'space-between', fontSize: '13px' }}>
                                  <span>{garment}</span>
                                  <span style={{ fontWeight: 600 }}>{count} ({pct}%)</span>
                                </div>
                                <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                                  <div style={{ width: `${pct}%`, height: '100%', background: 'var(--accent-color, #d4af37)', borderRadius: '3px' }}></div>
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
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Customer Segmentation</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                          {(() => {
                            const vipCount = customersList.filter(c => c.segment === 'VIP').length;
                            const hvcCount = customersList.filter(c => c.segment === 'HVC').length;
                            const generalCount = customersList.filter(c => c.segment === 'General').length;
                            const total = customersList.length || 1;

                            return [
                              { name: 'VIP (Very Important Customer)', count: vipCount, color: '#d4af37' },
                              { name: 'HVC (High Value Customer)', count: hvcCount, color: '#a855f7' },
                              { name: 'General Customers', count: generalCount, color: '#9ca3af' }
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
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Neckline & Sleeve Trends</h3>
                        <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                          <div>
                            <h4 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase' }}>Top Necklines</h4>
                            {topNecklinesList.map(([style, count], idx) => (
                              <div key={idx} style={{ fontSize: '13px', display: 'flex', justifycontent: 'space-between', padding: '4px 0' }}>
                                <span>{style}</span>
                                <span style={{ fontWeight: 600 }}>{count}</span>
                              </div>
                            ))}
                          </div>
                          <div>
                            <h4 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', textTransform: 'uppercase' }}>Top Sleeves</h4>
                            {topSleevesList.map(([style, count], idx) => (
                              <div key={idx} style={{ fontSize: '13px', display: 'flex', justifycontent: 'space-between', padding: '4px 0' }}>
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
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Staff & Workload Overview</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', fontSize: '14px' }}>
                          <div style={{ display: 'flex', justifycontent: 'space-between', alignItems: 'center' }}>
                            <span>Total Tailoring Team</span>
                            <span style={{ fontWeight: 600 }}>{tailors.length} Tailors</span>
                          </div>
                          <div style={{ display: 'flex', justifycontent: 'space-between', alignItems: 'center' }}>
                            <span>Busy / Assigned Tailors</span>
                            <span style={{ fontWeight: 600, color: '#ffc107' }}>{busyTailors} Busy</span>
                          </div>
                          <div style={{ display: 'flex', justifycontent: 'space-between', alignItems: 'center' }}>
                            <span>Available Staff capacity</span>
                            <span style={{ fontWeight: 600, color: '#2ec4b6' }}>{tailors.length - busyTailors} Free</span>
                          </div>
                          <div style={{ display: 'flex', justifycontent: 'space-between', alignItems: 'center' }}>
                            <span>Atelier Average Rating</span>
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
                        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Order Status Breakdown</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          {Object.entries(dashboardData?.stats?.status_distribution || {}).map(([status, count], idx) => {
                            const pct = Math.round((count / ordersList.length) * 100) || 0;
                            return (
                              <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                <div style={{ display: 'flex', justifycontent: 'space-between', fontSize: '13px' }}>
                                  <span>{status}</span>
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
                        My Account Settings
                      </h1>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Manage your boutique profile and atelier details.</p>
                    </div>
                  </div>
                  <div className="portal-header-right">
                    <div className="user-profile-widget">
                      <div className="user-avatar-circle">
                        <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100" alt="Avatar" />
                      </div>
                      <span>Hi, {currentUser.first_name}</span>
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
                      border: '3px solid var(--accent-color, #d4af37)'
                    }}>
                      <img src="https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=200" alt="Profile" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    </div>
                    <div>
                      <h3 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>{currentUser.first_name} {currentUser.last_name}</h3>
                      <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>Boutique Owner</p>
                    </div>
                    
                    <div style={{ width: '100%', height: '1px', background: 'var(--border-color, rgba(255,255,255,0.08))' }}></div>
                    
                    <div style={{ alignSelf: 'stretch', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
                      <div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: '11px', textTransform: 'uppercase' }}>Tenant Domain</div>
                        <div style={{ fontWeight: 600, color: 'var(--accent-color, #d4af37)' }}>
                          {localStorage.getItem('tenant_id') || 'Aditi\'s Boutique'}
                        </div>
                      </div>
                      <div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: '11px', textTransform: 'uppercase' }}>Atelier Email</div>
                        <div style={{ fontWeight: 600 }}>{currentUser.email}</div>
                      </div>
                      <div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: '11px', textTransform: 'uppercase' }}>Registered Since</div>
                        <div style={{ fontWeight: 600 }}>June 2024</div>
                      </div>
                    </div>
                  </div>

                  {/* Right editable profile settings */}
                  <div className="content-card">
                    <h3 className="card-title">Edit Boutique Profile</h3>
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
                        <label className="form-label">Boutique Name</label>
                        <input 
                          type="text" 
                          name="boutiqueName"
                          className="form-control" 
                          defaultValue={boutiqueSettings?.name || "Scaleezy Atelier"} 
                          required
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">Boutique Address</label>
                        <textarea 
                          name="boutiqueAddress"
                          className="form-control" 
                          style={{ minHeight: '80px', resize: 'vertical' }}
                          defaultValue={boutiqueSettings?.address || "123 Atelier Way, Fashion District"} 
                          required
                        />
                      </div>

                      <div className="form-grid-2">
                        <div className="form-group">
                          <label className="form-label">Boutique Phone</label>
                          <input 
                            type="text" 
                            name="boutiquePhone"
                            className="form-control" 
                            defaultValue={boutiqueSettings?.phone || "+91 9999999999"} 
                            required
                          />
                        </div>
                        <div className="form-group">
                          <label className="form-label">Boutique Email</label>
                          <input 
                            type="email" 
                            name="boutiqueEmail"
                            className="form-control" 
                            defaultValue={boutiqueSettings?.email || "contact@scaleezy.com"} 
                            required
                          />
                        </div>
                      </div>

                      <div className="form-group">
                        <label className="form-label">Boutique Logo</label>
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
                            <span style={{ fontWeight: 600 }}>Require approval for new designs</span>
                            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                              When on, uploads from staff other than you wait for your review before appearing in the library.
                            </div>
                          </span>
                        </label>
                      </div>

                      <button type="submit" className="btn-primary" style={{ alignSelf: 'flex-start', marginTop: '8px' }}>
                        Save Changes
                      </button>
                    </form>
                  </div>
                </div>
              </>
            )}
          </main>

          {/* Fabrics CRUD Modal Overlay */}
          {showFabricModal && (
            <div className="existing-customer-search-modal" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100 }}>
              <div className="search-modal-card" style={{ maxWidth: '500px', width: '100%' }}>
                <div className="search-modal-header">
                  <h3 style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--font-serif)' }}>
                    {editingFabric ? 'Edit Fabric Details' : 'Add New Fabric to Catalog'}
                  </h3>
                  <button className="close-btn" onClick={() => setShowFabricModal(false)}><X size={20} /></button>
                </div>
                
                <form onSubmit={handleSaveFabric} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Fabric Name</label>
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
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Material</label>
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
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Color</label>
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
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Price per Meter (₹)</label>
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
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Image URL (Optional)</label>
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
                    <label htmlFor="fabricAvailable" style={{ fontSize: '13px', cursor: 'pointer' }}>Available in Inventory</label>
                  </div>

                  <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px', marginTop: '8px' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShowFabricModal(false)}>Cancel</button>
                    <button type="submit" className="btn-primary">Save Fabric</button>
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
                  <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
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
                    {editingTailor ? 'Edit Tailor Details' : 'Add New Tailor Profile'}
                  </h3>
                  <button className="close-btn" onClick={() => setShowTailorModal(false)}><X size={20} /></button>
                </div>
                
                <form onSubmit={handleSaveTailor} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Tailor Name</label>
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
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Email Address (for login)</label>
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
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Specialty</label>
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
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Rating (1.0 — 5.0)</label>
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
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Status</label>
                      <select 
                        className="form-control"
                        value={tailorForm.status}
                        onChange={e => setTailorForm({...tailorForm, status: e.target.value})}
                      >
                        <option value="Available">Available</option>
                        <option value="Busy">Busy</option>
                      </select>
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Staff Role</label>
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

                  <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px', marginTop: '8px' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShowTailorModal(false)}>Cancel</button>
                    <button type="submit" className="btn-primary">Save Tailor</button>
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
                    Share Login Credentials
                  </h3>
                  <button className="close-btn" onClick={() => setShareCredsTailor(null)}><X size={20} /></button>
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                  <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                    Provide these credentials to <strong>{shareCredsTailor.name}</strong> so they can log in to view and manage their assignments.
                  </p>

                  <div style={{ background: 'rgba(0,0,0,0.02)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Login Portal URL</span>
                      <div style={{ fontWeight: 600, fontSize: '14px', marginTop: '2px', wordBreak: 'break-all' }}>{window.location.origin}</div>
                    </div>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Username / Email</span>
                      <div style={{ fontWeight: 600, fontSize: '14px', marginTop: '2px', wordBreak: 'break-all' }}>{shareCredsTailor.email}</div>
                    </div>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Temporary Password</span>
                      <div style={{ fontWeight: 600, fontSize: '14px', marginTop: '2px' }}>TailorSecure2026!</div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px', marginTop: '8px' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShareCredsTailor(null)}>Close</button>
                    
                    {/* Copy to Clipboard */}
                    <button 
                      type="button" 
                      className="btn-secondary" 
                      onClick={() => {
                        const txt = `Atelier Staff Login Credentials:\nPortal: ${window.location.origin}\nEmail: ${shareCredsTailor.email}\nPassword: TailorSecure2026!`;
                        navigator.clipboard.writeText(txt);
                        alert("Credentials copied to clipboard!");
                      }}
                      style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                      <Copy size={14} /> Copy
                    </button>

                    {/* Share via WhatsApp */}
                    <button 
                      type="button" 
                      className="btn-primary" 
                      onClick={() => {
                        const msg = encodeURIComponent(`Hello ${shareCredsTailor.name},\nHere are your Atelier login credentials:\nPortal: ${window.location.origin}\nEmail: ${shareCredsTailor.email}\nPassword: TailorSecure2026!\n\nPlease log in to view your supervised/stitch tasks.`);
                        window.open(`https://wa.me/?text=${msg}`);
                      }}
                      style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                      <MessageSquare size={14} /> Share WhatsApp
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
                    {editingDesign ? 'Edit Design Details' : 'Add New Design to Collection'}
                  </h3>
                  <button className="close-btn" onClick={() => setShowDesignModal(false)}><X size={20} /></button>
                </div>
                
                <form onSubmit={handleSaveDesign} style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Design Name</label>
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
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Garment Category</label>
                      <select 
                        className="form-control"
                        value={designForm.garment_type}
                        onChange={e => setDesignForm({...designForm, garment_type: e.target.value})}
                      >
                        <option value="Lehenga">Lehenga</option>
                        <option value="Gown">Gown</option>
                        <option value="Saree">Saree</option>
                        <option value="Kurti">Kurti</option>
                        <option value="Sherwani">Sherwani</option>
                        <option value="Anarkali">Anarkali</option>
                      </select>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Design Type</label>
                      <select 
                        className="form-control"
                        value={designForm.is_boutique}
                        onChange={e => setDesignForm({...designForm, is_boutique: e.target.value === 'true' || e.target.value === true})}
                      >
                        <option value="true">Boutique Catalog Collection</option>
                        <option value="false">AI Suggestion Template</option>
                      </select>
                    </div>
                  </div>

                  <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Neckline Style (Optional)</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="e.g. Sweetheart Neck" 
                        value={designForm.neckline_style}
                        onChange={e => setDesignForm({...designForm, neckline_style: e.target.value})}
                      />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '12px', fontWeight: 600 }}>Sleeve Style (Optional)</label>
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
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Catalog Price (₹) - Only for Boutique Catalog</label>
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
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Image URL (Optional)</label>
                    <input 
                      type="url" 
                      className="form-control" 
                      placeholder="e.g. https://images.unsplash.com/photo-..." 
                      value={designForm.image_url}
                      onChange={e => setDesignForm({...designForm, image_url: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600 }}>Description (Optional)</label>
                    <textarea 
                      className="form-control" 
                      placeholder="e.g. Hand-embroidered with gold thread, georgette base..." 
                      rows="3"
                      value={designForm.description}
                      onChange={e => setDesignForm({...designForm, description: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '16px', marginTop: '8px' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShowDesignModal(false)}>Cancel</button>
                    <button type="submit" className="btn-primary">Save Design</button>
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
                .then(() => fetchNotifications());
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
              <a className="portal-menu-item" onClick={() => { setMobileNavOpen(false); setView('dashboard'); }}><Users size={16} /> Dashboard</a>
              <a className="portal-menu-item"><ShoppingBag size={16} /> My Orders</a>
              <a className="portal-menu-item"><Calendar size={16} /> Appointments</a>
              <a className="portal-menu-item"><Scissors size={16} /> Measurements</a>
              <a className="portal-menu-item" onClick={handleLogout}><User size={16} /> Logout</a>
            </nav>
          </aside>

          <main className="portal-main">
            <div className="selector-container">
              <div className="selector-header">
                <h1 className="selector-title" style={{ fontFamily: 'var(--font-serif)', fontSize: '32px' }}>Create New Custom Order</h1>
                <p className="selector-subtitle" style={{ color: 'var(--text-secondary)' }}>Choose how you would like to initiate this bespoke order creation.</p>
              </div>

              <div className="selector-cards-grid">
                {/* Option 1: Existing Customer */}
                <div className="selector-option-card" onClick={openExistingCustomerModal}>
                  <div className="selector-option-icon">
                    <Users size={32} />
                  </div>
                  <h3 className="selector-option-title">Existing Customer</h3>
                  <p className="selector-option-desc">Select a client profile from your database and retrieve their measurements.</p>
                  
                  <div className="selector-features-list">
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>Use saved measurements</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>View past orders & prefs</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>Faster order creation</span>
                    </div>
                  </div>

                  <button className="selector-card-btn">
                    Select Existing Customer
                    <ArrowRight size={14} />
                  </button>
                </div>

                {/* Option 2: New Customer */}
                <div className="selector-option-card" onClick={handleStartNewCustomer}>
                  <div className="selector-option-icon">
                    <User size={32} />
                  </div>
                  <h3 className="selector-option-title">New Customer</h3>
                  <p className="selector-option-desc">Create a new customer profile and input their measurements from scratch.</p>

                  <div className="selector-features-list">
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>Add customer details</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>Capture measurements</span>
                    </div>
                    <div className="selector-feature-item">
                      <Check size={14} />
                      <span>Start custom journey</span>
                    </div>
                  </div>

                  <button className="selector-card-btn">
                    Create New Customer
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>

              {/* Explanatory Flow Diagrams at the bottom */}
              <div className="selector-flow-explain-box">
                <h4 className="selector-flow-explain-title">How the creation process works</h4>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
                  {/* Flow with Existing Customer */}
                  <div>
                    <h5 style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '16px' }}>FLOW WITH EXISTING CUSTOMER:</h5>
                    <div className="flow-steps-visual">
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><Users size={16} /></div>
                        <span className="flow-step-node-title">Select Customer</span>
                        <span className="flow-step-node-desc">Search and select client from database</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><FileText size={16} /></div>
                        <span className="flow-step-node-title">Review Profile</span>
                        <span className="flow-step-node-desc">Check sizes and preferences</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><Sparkles size={16} /></div>
                        <span className="flow-step-node-title">Create Order</span>
                        <span className="flow-step-node-desc">Define styles, fabrics and details</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node completed">
                        <div className="flow-step-icon-circle"><Check size={16} /></div>
                        <span className="flow-step-node-title">Proceed to Journey</span>
                        <span className="flow-step-node-desc">Stitching and fitting commences</span>
                      </div>
                    </div>
                  </div>

                  {/* Flow with New Customer */}
                  <div>
                    <h5 style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '16px' }}>FLOW WITH NEW CUSTOMER:</h5>
                    <div className="flow-steps-visual">
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><User size={16} /></div>
                        <span className="flow-step-node-title">Add Personal Details</span>
                        <span className="flow-step-node-desc">Input names and contact credentials</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><Scissors size={16} /></div>
                        <span className="flow-step-node-title">Capture Sizes</span>
                        <span className="flow-step-node-desc">Log exact body dimensions</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><Compass size={16} /></div>
                        <span className="flow-step-node-title">Style Preferences</span>
                        <span className="flow-step-node-desc">Choose fabrics, cuts, necklines</span>
                      </div>
                      <div className="flow-step-arrow"></div>
                      <div className="flow-step-node">
                        <div className="flow-step-icon-circle"><ArrowRight size={16} /></div>
                        <span className="flow-step-node-title">Proceed to Journey</span>
                        <span className="flow-step-node-desc">Submit for creation workflow</span>
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
                  <h3 style={{ fontSize: '16px', fontWeight: 600 }}>Select Existing Customer</h3>
                  <button className="close-btn" onClick={() => setShowSearchModal(false)}><X size={20} /></button>
                </div>
                
                <div className="search-input-wrapper" style={{ width: '100%' }}>
                  <Search size={18} />
                  <input 
                    type="text" 
                    placeholder="Search by customer name or mobile number..." 
                    value={searchModalQuery}
                    onChange={(e) => setSearchModalQuery(e.target.value)}
                    className="form-control"
                    autoFocus
                  />
                </div>

                <div className="search-results-list">
                  {filteredSearchModalCustomers.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '13px' }}>
                      No customers found matching "{searchModalQuery}"
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
                          <div className="search-result-phone">📞 {cust.mobile_number}</div>
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
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  <HelpCircle size={16} /> Need help?
                </span>
                <span style={{ cursor: 'pointer', color: 'var(--text-secondary)' }} onClick={() => setView('dashboard')}>
                  <X size={20} />
                </span>
              </div>
            </div>
            
            {/* Stepper progress bar */}
            <div className="stepper-progress-bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', maxWidth: '1000px', margin: '0 auto', position: 'relative' }}>
              {[
                { number: 1, label: 'Personal details', sub: 'Completed' },
                { number: 2, label: 'Measurements', sub: 'Completed' },
                { number: 3, label: 'AI Design Studio', sub: 'Discover & approve design' },
                { number: 4, label: 'Fabric Selection', sub: 'Choose fabrics' },
                { number: 5, label: 'Tailor Assignment', sub: 'Assign tailor' },
                { number: 6, label: 'Complete & Create Order', sub: 'review & confirm' }
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
                        {isActive ? 'review & confirm' : (isCompleted ? 'Completed' : step.sub)}
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
            {/* STEP 1: Personal Details */}
            {currentStep === 1 && (
              <>
                <div className="page-title-group">
                  <h1 className="page-title">Create Customer</h1>
                  <p className="page-subtitle">Onboard new clients into the Scaleezy ecosystem. Capture style preferences and measurements for a personalized atelier experience.</p>
                </div>

                <div className="content-card">
                  <div className="card-title">
                    <Users size={20} />
                    Customer Profile
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
                        Upload Photo
                        <input 
                          type="file" 
                          id="profile-picker" 
                          accept="image/*" 
                          style={{ display: 'none' }} 
                          onChange={handleProfilePhotoChange}
                        />
                      </label>
                      <span className="upload-btn-sub">JPG, PNG up to 5MB</span>
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">First Name <span className="required">*</span></label>
                      <input 
                        type="text" 
                        value={customerForm.first_name}
                        onChange={(e) => setCustomerForm({...customerForm, first_name: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. Amara"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Last Name <span className="required">*</span></label>
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
                      <label className="form-label">Mobile Number <span className="required">*</span></label>
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
                      <label className="form-label">Email Address <span className="required">*</span></label>
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
                    <label className="form-label">Address <span className="required">*</span></label>
                    <input 
                      type="text" 
                      value={customerForm.address || ''}
                      onChange={(e) => setCustomerForm({...customerForm, address: e.target.value})}
                      className="form-control" 
                      placeholder="Street name, Apartment, City, State, PIN code"
                    />
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">City / Region</label>
                      <input 
                        type="text" 
                        value={customerForm.city_region || ''}
                        onChange={(e) => setCustomerForm({...customerForm, city_region: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. New Delhi"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Source</label>
                      <select 
                        value={customerForm.source}
                        onChange={(e) => setCustomerForm({...customerForm, source: e.target.value})}
                        className="form-control"
                      >
                        <option value="Walk In">Walk In</option>
                        <option value="Instagram">Instagram</option>
                        <option value="Referral">Referral</option>
                        <option value="Website">Website</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">Customer Type</label>
                      <select 
                        value={customerForm.customer_type}
                        onChange={(e) => setCustomerForm({...customerForm, customer_type: e.target.value})}
                        className="form-control"
                      >
                        <option value="Women">Women</option>
                        <option value="Men">Men</option>
                        <option value="Kids">Kids</option>
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
                      Dresses in this Order <span className="required">*</span>
                    </label>
                    <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                      Pick every garment being stitched. Each one gets its own measurements and options.
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
                    {/* An empty picker used to render as a blank box with no
                        explanation, which looks identical to "the boutique has
                        no garments" and leaves the order form unusable. Say what
                        went wrong and offer the retry. */}
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
                          Retry
                        </button>
                      </div>
                    )}
                    {garmentTemplates.length > 0 && garmentJobs.length === 0 && (
                      <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginTop: '12px' }}>
                        No garment chosen yet.
                      </div>
                    )}
                  </div>

                  <div className="form-grid-2">
                    <div className="form-group">
                      <label className="form-label">Pattern Style</label>
                      <select 
                        value={customerForm.pattern_style || ''}
                        onChange={(e) => setCustomerForm({...customerForm, pattern_style: e.target.value})}
                        className="form-control"
                      >
                        <option value="">Select Pattern Style</option>
                        <option value="Floral Prints">Floral Prints</option>
                        <option value="Traditional Brocade">Traditional Brocade</option>
                        <option value="Solid Plain">Solid Plain</option>
                        <option value="Geometrical">Geometrical</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Occasion</label>
                      <select 
                        value={customerForm.occasion || ''}
                        onChange={(e) => setCustomerForm({...customerForm, occasion: e.target.value})}
                        className="form-control"
                      >
                        <option value="">Select Occasion</option>
                        <option value="Wedding / Bridal">Wedding / Bridal</option>
                        <option value="Festive wear">Festive wear</option>
                        <option value="Formal Event">Formal Event</option>
                        <option value="Casual wear">Casual wear</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Custom Requirements</label>
                    <textarea 
                      value={customerForm.custom_requirements || ''}
                      onChange={(e) => setCustomerForm({...customerForm, custom_requirements: e.target.value})}
                      className="form-control"
                      placeholder="Specify custom preferences (e.g. padding, side zippers, extra margin)"
                    />
                  </div>
                </div>

                {/* Additional Information Card */}
                <div className="content-card">
                  <div className="card-title">
                    <FolderOpen size={20} />
                    Additional Information
                  </div>

                  <div className="form-grid-3">
                    <div className="form-group">
                      <label className="form-label">Date of Birth</label>
                      <input 
                        type="date" 
                        value={customerForm.date_of_birth || ''}
                        onChange={(e) => setCustomerForm({...customerForm, date_of_birth: e.target.value})}
                        className="form-control"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Occupation</label>
                      <input 
                        type="text" 
                        value={customerForm.occupation || ''}
                        onChange={(e) => setCustomerForm({...customerForm, occupation: e.target.value})}
                        className="form-control" 
                        placeholder="e.g. Entrepreneur"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Preferred Communication</label>
                      <select 
                        value={customerForm.preferred_communication}
                        onChange={(e) => setCustomerForm({...customerForm, preferred_communication: e.target.value})}
                        className="form-control"
                      >
                        <option value="WhatsApp">WhatsApp</option>
                        <option value="Call">Phone Call</option>
                        <option value="Email">Email</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Notes</label>
                    <textarea 
                      value={customerForm.notes || ''}
                      onChange={(e) => setCustomerForm({...customerForm, notes: e.target.value})}
                      className="form-control"
                      placeholder="Any additional notes about the customer..."
                    />
                  </div>
                </div>
              </>
            )}

            {/* STEP 2: Measurements */}
            {currentStep === 2 && (
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
                          />
                        </div>
                      );
                    })}
                  </div>
                ))}
              </>
            )}

            {/* STEP 3: AI Design Studio */}
            {currentStep === 3 && (
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
                      <DesignStudio
                        customerId={customerId}
                        orderInput={{
                          garment_type: customerForm.garment_type,
                          occasion: customerForm.occasion,
                          budget: quotePrices.base
                        }}
                        notes={designNotes}
                        onNotesChange={setDesignNotes}
                        onBoardChange={setDesignBoard}
                      />
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

            {/* STEP 4: Fabric Selection */}
            {currentStep === 4 && (
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
                                  <img src={resolvedImg} alt={f.name} onError={(e) => {
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
                                  <span className="fabric-price">₹{f.price_per_meter.toLocaleString('en-IN')} / mtr</span>
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
                      <Sparkles size={20} style={{ color: 'var(--accent-color, #d4af37)' }} />
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
                  <h1 className="page-title">Review & Staff Assignment</h1>
                  <p className="page-subtitle">Assign a Master Tailor to supervise/cut and a Stitching Tailor for the assembly.</p>
                </div>

                <div className="responsive-profile-grid" style={{ gap: '24px' }}>
                  {/* Master Assignment Card */}
                  <div className="content-card" style={{ margin: 0 }}>
                    <div className="card-title">
                      <Scissors size={20} style={{ color: 'var(--accent-color, #d4af37)' }} />
                      1. Assign Master Tailor (Cutting & Supervision)
                    </div>
                    <div className="tailors-list" style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {tailors.filter(t => t.role === 'Master').length === 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '8px 0' }}>
                          <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>No Master Tailors available. Add one to continue:</div>
                          <button 
                            className="btn-primary" 
                            style={{ alignSelf: 'flex-start', padding: '8px 16px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
                            onClick={() => {
                              setEditingTailor(null);
                              setTailorForm({ name: '', email: '', specialty: 'Ethnic & Bridal Cutting', rating: 5.0, status: 'Available', role: 'Master' });
                              setShowTailorModal(true);
                            }}
                          >
                            <Plus size={14} /> Add Master Tailor
                          </button>
                        </div>
                      ) : (
                        tailors.filter(t => t.role === 'Master').map(t => (
                          <div 
                            key={t.id} 
                            className={`tailor-row ${selectedMaster?.id === t.id ? 'selected' : ''}`}
                            onClick={() => setSelectedMaster(t)}
                            style={{
                              display: 'flex',
                              gap: '16px',
                              alignItems: 'center',
                              padding: '12px',
                              borderRadius: '8px',
                              border: selectedMaster?.id === t.id ? '2px solid var(--accent-color, #d4af37)' : '1px solid var(--border-color)',
                              background: selectedMaster?.id === t.id ? 'rgba(212, 175, 55, 0.05)' : 'transparent',
                              cursor: 'pointer'
                            }}
                          >
                            <div style={{ width: '40px', height: '40px', borderRadius: '50%', overflow: 'hidden', flexShrink: 0 }}>
                              <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(t.name)}`} alt={t.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            </div>
                            <div className="tailor-info" style={{ flex: 1 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>{t.name}</span>
                                <span className={`order-row-badge ${t.status === 'Available' ? 'confirmed' : 'in_progress'}`} style={{ fontSize: '10px', padding: '1px 6px' }}>
                                  {t.status}
                                </span>
                              </div>
                              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{t.specialty}</span>
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
                      2. Assign Stitching Tailor (Sewing & Details)
                    </div>
                    <div className="tailors-list" style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {tailors.filter(t => t.role !== 'Master').length === 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '8px 0' }}>
                          <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>No Stitching Tailors available. Add one to continue:</div>
                          <button 
                            className="btn-primary" 
                            style={{ alignSelf: 'flex-start', padding: '8px 16px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
                            onClick={() => {
                              setEditingTailor(null);
                              setTailorForm({ name: '', email: '', specialty: 'Assembly & Detailing', rating: 5.0, status: 'Available', role: 'Tailor' });
                              setShowTailorModal(true);
                            }}
                          >
                            <Plus size={14} /> Add Stitching Tailor
                          </button>
                        </div>
                      ) : (
                        tailors.filter(t => t.role !== 'Master').map(t => (
                          <div 
                            key={t.id} 
                            className={`tailor-row ${selectedTailor?.id === t.id ? 'selected' : ''}`}
                            onClick={() => setSelectedTailor(t)}
                            style={{
                              display: 'flex',
                              gap: '16px',
                              alignItems: 'center',
                              padding: '12px',
                              borderRadius: '8px',
                              border: selectedTailor?.id === t.id ? '2px solid var(--border-color)' : '1px solid var(--border-color)',
                              background: selectedTailor?.id === t.id ? 'rgba(0, 0, 0, 0.03)' : 'transparent',
                              cursor: 'pointer'
                            }}
                          >
                            <div style={{ width: '40px', height: '40px', borderRadius: '50%', overflow: 'hidden', flexShrink: 0 }}>
                              <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(t.name)}`} alt={t.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            </div>
                            <div className="tailor-info" style={{ flex: 1 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>{t.name}</span>
                                <span className={`order-row-badge ${t.status === 'Available' ? 'confirmed' : 'in_progress'}`} style={{ fontSize: '10px', padding: '1px 6px' }}>
                                  {t.status}
                                </span>
                              </div>
                              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{t.specialty}</span>
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
                    <Compass size={20} style={{ color: 'var(--accent-color, #d4af37)' }} />
                    3. Delivery Method Configuration
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
                        Direct Boutique Pickup
                      </label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>
                        <input 
                          type="radio" 
                          name="deliveryMethod" 
                          value="Courier"
                          checked={deliveryMethod === 'Courier'}
                          onChange={() => setDeliveryMethod('Courier')}
                        />
                        Courier Delivery
                      </label>
                    </div>

                    {deliveryMethod === 'Courier' && (
                      <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', background: 'rgba(0,0,0,0.02)', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-color)', marginTop: '8px' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          <label style={{ fontSize: '12px', fontWeight: 600 }}>Courier Service Provider</label>
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
                          <label style={{ fontSize: '12px', fontWeight: 600 }}>Tracking Reference Number</label>
                          <input 
                            type="text" 
                            className="form-control"
                            placeholder="e.g. 123456789"
                            value={trackingNumber}
                            onChange={(e) => setTrackingNumber(e.target.value)}
                          />
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', gridColumn: 'span 2' }}>
                          <label style={{ fontSize: '12px', fontWeight: 600 }}>Shipping / Delivery Address</label>
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
                                ? garmentJobs.map(job => job.template.name).join(', ')
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
                        <div style={{ display: 'flex', alignItems: 'center', gap: '20px', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                          <div style={{ width: '48px', height: '48px', borderRadius: '50%', overflow: 'hidden', flexShrink: 0 }}>
                            <img src={getTailorAvatarUrl(selectedTailor.name)} alt={selectedTailor.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          </div>
                          <div style={{ flex: 1 }}>
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
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginTop: '4px' }}>📞 +91 {customerForm.mobile_number}</span>
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
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>+91 {customerForm.mobile_number}</span>
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
                              <span style={{ fontSize: '12px', fontWeight: 600 }}>{customerForm.customer_type} • {customerForm.garment_type}</span>
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
                            ₹{getTotalPrice().toLocaleString('en-IN')}
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
                              <span style={{ fontSize: '16px', fontWeight: 700 }}>₹{Math.max(0, getTotalPrice() - (advancePaymentAmount || getTotalPrice() / 2)).toLocaleString('en-IN')}</span>
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
                    How it works
                  </div>
                  <div className="instruction-steps">
                    <div className="instruction-step">
                      <div className="step-num-badge">1</div>
                      <div className="instruction-step-content">
                        <span className="instruction-step-title">Enter Profile Details</span>
                        <span className="instruction-step-desc">Provide size tags and contact channels.</span>
                      </div>
                    </div>
                    <div className="instruction-step">
                      <div className="step-num-badge">2</div>
                      <div className="instruction-step-content">
                        <span className="instruction-step-title">Submit Measurements</span>
                        <span className="instruction-step-desc">Collect 7 key body specifications.</span>
                      </div>
                    </div>
                    <div className="instruction-step">
                      <div className="step-num-badge">3</div>
                      <div className="instruction-step-content">
                        <span className="instruction-step-title">Bespoke Design & Fabric</span>
                        <span className="instruction-step-desc">Pick reference sketches and fabric rolls.</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="sidebar-card">
                  <div className="sidebar-card-title">
                    <ShieldCheck size={16} />
                    Privacy Assured
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    Customer details, style files, and measurement records are saved exclusively to the Scaleezy database cluster and never shared.
                  </p>
                </div>
              </>
            ) : currentStep === 5 ? (
              <div className="sidebar-card">
                <div className="sidebar-card-title">
                  <ShoppingBag size={18} />
                  Order Summary
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px' }}>
                  <div style={{ fontSize: '14px', fontWeight: 600 }}>{customerForm.customer_type} • {customerForm.garment_type}</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                    Fabric: {fabricTab === 'boutique' && selectedFabric ? `${selectedFabric.name} (${selectedFabric.color})` : 'Customer fabric'}
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div className="summary-item-row">
                    <span>Base Price ({customerForm.garment_type})</span>
                    <span className="price-display">₹{parseFloat(quotePrices.base || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Fabric Charges (3 mtr)</span>
                    <span className="price-display">₹{parseFloat(quotePrices.fabric || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Embroidery & Artisan Work</span>
                    <span className="price-display">₹{parseFloat(quotePrices.embroidery || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Customization Charge</span>
                    <span className="price-display">₹{parseFloat(quotePrices.customization || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Tailoring Charges</span>
                    <span className="price-display">₹{parseFloat(quotePrices.tailoring || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Packaging & Handling</span>
                    <span className="price-display">₹{parseFloat(quotePrices.packaging || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row" style={{ borderTop: '1px solid #f1f3f5', paddingTop: '10px' }}>
                    <span>Subtotal</span>
                    <span className="price-display">₹{getSubtotal().toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row">
                    <span>Taxes (GST 5%)</span>
                    <span className="price-display">₹{getTaxes().toLocaleString('en-IN')}</span>
                  </div>
                  <div className="summary-item-row total">
                    <span>Total Amount</span>
                    <span className="price-display total">₹{getTotalPrice().toLocaleString('en-IN')}</span>
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
                      {customerForm.customer_type} • {garmentJobs.length
                        ? garmentJobs.map(job => job.template.name).join(', ')
                        : customerForm.garment_type}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                      Fabric: {fabricTab === 'boutique' && selectedFabric ? `${selectedFabric.name} (${selectedFabric.color})` : 'Customer fabric'}
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px', marginTop: '16px' }}>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Base Price ({customerForm.garment_type})</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.base || 0).toLocaleString('en-IN')}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input 
                            type="number" 
                            value={quotePrices.base} 
                            onChange={(e) => setQuotePrices({...quotePrices, base: e.target.value})} 
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Fabric ({selectedFabric ? selectedFabric.name : (fabricPreviews.length > 0 ? 'Uploaded Fabric' : 'Customer Fabric')})</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.fabric || 0).toLocaleString('en-IN')}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input 
                            type="number" 
                            value={quotePrices.fabric} 
                            onChange={(e) => setQuotePrices({...quotePrices, fabric: e.target.value})} 
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Embroidery & Work</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.embroidery || 0).toLocaleString('en-IN')}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input 
                            type="number" 
                            value={quotePrices.embroidery} 
                            onChange={(e) => setQuotePrices({...quotePrices, embroidery: e.target.value})} 
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Customization</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.customization || 0).toLocaleString('en-IN')}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input 
                            type="number" 
                            value={quotePrices.customization} 
                            onChange={(e) => setQuotePrices({...quotePrices, customization: e.target.value})} 
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Tailoring Charges</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.tailoring || 0).toLocaleString('en-IN')}</span>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>₹</span>
                          <input 
                            type="number" 
                            value={quotePrices.tailoring} 
                            onChange={(e) => setQuotePrices({...quotePrices, tailoring: e.target.value})} 
                            style={{ width: '85px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '12px', textAlign: 'right', fontWeight: 600 }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="summary-item-row" style={{ alignItems: 'center' }}>
                      <span>Packaging & Handling</span>
                      {paymentPhase ? (
                        <span className="price-display">₹{parseFloat(quotePrices.packaging || 0).toLocaleString('en-IN')}</span>
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
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '16px' }}>
                    <div className="summary-item-row" style={{ fontWeight: 600 }}>
                      <span>Subtotal</span>
                      <span className="price-display">₹{getSubtotal().toLocaleString('en-IN')}</span>
                    </div>
                    <div className="summary-item-row">
                      <span>Taxes (GST 5%)</span>
                      <span className="price-display">₹{getTaxes().toLocaleString('en-IN')}</span>
                    </div>
                    <div className="summary-item-row total" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '12px' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        Total Amount <HelpCircle size={12} style={{ color: 'var(--text-secondary)' }} />
                      </span>
                      <span className="price-display total" style={{ color: '#107c41', fontSize: '20px', fontWeight: 700 }}>
                        ₹{getTotalPrice().toLocaleString('en-IN')}
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
                style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', color: 'var(--text-secondary)' }}
                onClick={() => {
                  navigator.clipboard.writeText(confirmedOrder.order_id);
                  alert("Copied!");
                }}
              >
                <Copy size={14} />
              </button>
            </div>
          </div>

          <div className="order-meta-info-grid">
            <div className="meta-info-block">
              <span className="meta-info-label">Order Date</span>
              <span className="meta-info-val">
                {new Date(confirmedOrder.order_date).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
              </span>
            </div>
            <div className="meta-info-block">
              <span className="meta-info-label">Payment Status</span>
              <span className="meta-info-val" style={{ color: 'var(--success-color)' }}>
                Paid • ₹{confirmedOrder.total_amount.toLocaleString('en-IN')}
              </span>
            </div>
            <div className="meta-info-block">
              <span className="meta-info-label">Estimated Delivery</span>
              <span className="meta-info-val">
                {new Date(confirmedOrder.estimated_delivery).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
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
            <button className="whatsapp-btn" onClick={() => window.open(`https://wa.me/91${customerForm.mobile_number}`)}>
              <MessageSquare size={18} />
              Chat on WhatsApp
            </button>
          </div>

          <div style={{ display: 'flex', gap: '16px', justifyContent: 'center', width: '100%', maxWidth: '450px' }}>
            <button className="btn-secondary" style={{ flex: 1, justifyContent: 'center' }} onClick={() => { setView('dashboard'); fetchDashboardAndConfig(); }}>
              Back to Dashboard
            </button>
            <button className="btn-primary" style={{ flex: 1, justifyContent: 'center', backgroundColor: '#0f291e' }} onClick={() => setShowInvoiceModal(true)}>
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
              Back
            </button>
          </div>
          <div className="footer-right-actions">
            {/* Show Save as Draft only if they are creating a new customer profile (Step 1 or 2) */}
            {currentStep < 3 && (
              <button className="btn-secondary" onClick={handleSaveDraft} disabled={ctaBusy}>
                Save as Draft
              </button>
            )}
            <button className="btn-primary" onClick={handleNext} disabled={ctaBusy} style={{ opacity: ctaBusy ? 0.6 : 1 }}>
              {ctaBusy ? 'Working…' : <>{currentStep === 5 ? 'Confirm Order' : 'Next'}<ArrowRight size={16} /></>}
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
                    Date: {new Date(confirmedOrder.order_date).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
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
                  <span style={{ display: 'block', color: 'var(--text-secondary)' }}>📞 +91 {confirmedOrder.customer_mobile}</span>
                  {confirmedOrder.customer_email && <span style={{ display: 'block', color: 'var(--text-secondary)' }}>✉️ {confirmedOrder.customer_email}</span>}
                </div>
                <div>
                  <span style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>Atelier Details:</span>
                  <span style={{ fontSize: '14px', fontWeight: 700, display: 'block' }}>{boutiqueSettings?.name || "Scaleezy Boutique Portal"}</span>
                  <span style={{ display: 'block', color: 'var(--text-secondary)', marginTop: '4px' }}>📍 {boutiqueSettings?.address || "123 Atelier Way, Fashion District"}</span>
                  <span style={{ display: 'block', color: 'var(--text-secondary)' }}>📞 {boutiqueSettings?.phone || "+91 9999999999"}</span>
                  <span style={{ display: 'block', color: 'var(--text-secondary)' }}>✉️ {boutiqueSettings?.email || "contact@scaleezy.com"}</span>
                  <span style={{ display: 'block', color: 'var(--text-secondary)', marginTop: '4px' }}>Boutique Owner: {currentUser?.first_name || 'Aditi'} {currentUser?.last_name || 'Mehta'}</span>
                  {confirmedOrder.tailor_name && (
                    <span style={{ display: 'block', color: 'var(--text-secondary)', marginTop: '4px' }}>
                      Assigned Tailor: <strong>{confirmedOrder.tailor_name}</strong>
                    </span>
                  )}
                  <span style={{ display: 'block', color: 'var(--text-secondary)' }}>Estimated Delivery: {new Date(confirmedOrder.estimated_delivery).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                </div>
              </div>

              {/* Garment Details Summary */}
              <div style={{ backgroundColor: '#fcfdfd', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '16px', marginBottom: '32px' }}>
                <h4 style={{ fontSize: '12px', fontWeight: 700, margin: '0 0 12px 0', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Design & Specifications</h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', fontSize: '11px' }}>
                  <div>
                    <span style={{ color: 'var(--text-secondary)', display: 'block' }}>Garment Type</span>
                    <strong style={{ fontSize: '12px' }}>{confirmedOrder.customer_type} • {confirmedOrder.customer_garment_type}</strong>
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
                  <tr style={{ borderBottom: '2px solid #eaecef' }}>
                    <td style={{ padding: '16px 8px' }}>
                      <strong style={{ fontSize: '14px', color: '#0f291e' }}>Bespoke Handcrafted {confirmedOrder.customer_garment_type}</strong>
                      <span style={{ display: 'block', fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                        Custom garment design tailored to individual measurement specifications.
                      </span>
                      <span style={{ display: 'block', fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                        Fabric: {Number(confirmedOrder.fabric_price) > 0 ? `Boutique fabric — ₹${confirmedOrder.fabric_price}` : 'Customer Supplied Fabric'}
                      </span>
                    </td>
                    <td style={{ padding: '16px 8px', textAlign: 'right', fontWeight: 700, fontSize: '14px' }}>
                      ₹{parseFloat(confirmedOrder.total_amount || 0).toLocaleString('en-IN')}
                    </td>
                  </tr>
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
                      ₹{(parseFloat(confirmedOrder.total_amount || 0) - parseFloat(confirmedOrder.taxes || 0)).toLocaleString('en-IN')}
                    </strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '11px', color: 'var(--text-secondary)' }}>
                    <span>Taxes (GST 5%)</span>
                    <strong style={{ fontWeight: 600 }}>₹{parseFloat(confirmedOrder.taxes || 0).toLocaleString('en-IN')}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 0 6px 0', borderTop: '2px solid #0f291e', fontSize: '16px' }}>
                    <span style={{ fontWeight: 700, color: '#0f291e' }}>Total Amount</span>
                    <strong style={{ fontWeight: 800, color: '#107c41' }}>₹{parseFloat(confirmedOrder.total_amount || 0).toLocaleString('en-IN')}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '11px', color: 'var(--text-secondary)', borderTop: '1px solid #eaecef', marginTop: '6px' }}>
                    <span>Payment Status</span>
                    <strong style={{ fontWeight: 600 }}>{confirmedOrder.payment_status}</strong>
                  </div>
                  {confirmedOrder.advance_paid > 0 && (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '11px', color: 'var(--text-secondary)' }}>
                        <span>Advance Paid</span>
                        <strong style={{ fontWeight: 600 }}>₹{parseFloat(confirmedOrder.advance_paid).toLocaleString('en-IN')}</strong>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '11px', color: 'var(--text-secondary)' }}>
                        <span>Balance Due</span>
                        <strong style={{ fontWeight: 600 }}>₹{(parseFloat(confirmedOrder.total_amount) - parseFloat(confirmedOrder.advance_paid)).toLocaleString('en-IN')}</strong>
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
              <Bell size={20} style={{ color: 'var(--accent-color, #d4af37)' }} />
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
                {activeReviewOrder.garment_jobs.map(job => (
                  <div key={job.id} style={{ marginBottom: '10px' }}>
                    <div style={{ fontWeight: 600, marginBottom: '4px' }}>{job.template_name || job.template_key}</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '4px 12px' }}>
                      {Object.entries(job.measurements || {}).map(([k, v]) => (
                        <span key={k} style={{ color: 'var(--text-secondary)' }}>
                          {k.replace(/_/g, ' ')}: <strong style={{ color: 'var(--text-primary)' }}>{String(v)}</strong>
                        </span>
                      ))}
                      {Object.entries(job.spec || {})
                        .filter(([, v]) => v !== '' && v !== null && v !== undefined)
                        .map(([k, v]) => (
                          <span key={k} style={{ color: 'var(--text-secondary)' }}>
                            {k.replace(/_/g, ' ')}: <strong style={{ color: 'var(--text-primary)' }}>{String(v)}</strong>
                          </span>
                        ))}
                    </div>
                  </div>
                ))}
                {activeReviewOrder.special_instructions && (
                  <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid var(--border-color)' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Special instructions: </span>
                    <strong>{activeReviewOrder.special_instructions}</strong>
                  </div>
                )}
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

              {/* Performer Assignment Dropdown */}
              {(!currentUser.role || currentUser.role === 'Owner' || currentUser.role === 'Master') && (
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Assign Performer (Staff/Tailor)</label>
                  <select 
                    className="form-control"
                    style={{ fontSize: '12px', padding: '6px' }}
                    value={selectedPerformerId}
                    onChange={(e) => setSelectedPerformerId(e.target.value)}
                  >
                    <option value="">-- Select Tailor / Master --</option>
                    {tailors.map(t => (
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={20} style={{ color: 'var(--accent-color, #d4af37)' }} />
                <h3 style={{ fontSize: '18px', fontWeight: 700, margin: 0, letterSpacing: '0.5px' }}>Scaleezy Live Visualizer: Interactive Fabric Draping</h3>
              </div>
              <button 
                type="button"
                onClick={() => { setShowDrapingModal(false); }}
                style={{ background: 'none', border: 'none', color: '#888', fontSize: '20px', cursor: 'pointer', outline: 'none' }}
              >
                &times;
              </button>
            </div>

            {/* Modal Content Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1.2fr 1.6fr', gap: '20px', alignItems: 'stretch' }}>
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
                    <div style={{ color: 'var(--accent-color, #d4af37)', marginBottom: '12px' }}><Sparkles size={36} /></div>
                    <h4 style={{ fontSize: '14px', fontWeight: 600, color: '#fff', marginBottom: '8px' }}>Ready to Drape</h4>
                    <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '16px', maxWidth: '220px', margin: '0 auto 16px' }}>
                      Click "Start Try On" to simulate draping this fabric onto the mannequin.
                    </p>
                  </div>
                ) : drapingLoading ? (
                  <div style={{ textAlign: 'center', padding: '20px' }}>
                    <div className="spinner" style={{ border: '3px solid rgba(255,255,255,0.1)', borderTop: '3px solid var(--accent-color, #d4af37)', borderRadius: '50%', width: '40px', height: '40px', animation: 'modalSpin 1s linear infinite', margin: '0 auto 16px' }} />
                    <h4 style={{ fontSize: '14px', fontWeight: 600, color: '#fff', marginBottom: '4px' }}>Simulating Try On...</h4>
                    <p style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic' }}>Mapping coordinates onto sketch layers</p>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px', width: '100%' }}>
                    <span style={{ fontSize: '11px', color: 'var(--accent-color, #d4af37)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1px' }}>✨ 3D Mannequin Draped View</span>
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
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '8px' }}>
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
