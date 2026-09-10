import { useRef, useState } from 'react';
import {
  ArrowRight, Search, X as CloseIcon, Upload as UploadIcon, Camera as CameraIcon, Plus as PlusIcon,
  Lightbulb as LightbulbIcon, CheckCircle2 as CheckIcon,
} from 'lucide-react';

/**
 * The atelier design layer: the handful of shapes every workspace screen is
 * built from, so a stat reads the same on Orders as it does on Payroll.
 *
 *   PageHeader   what screen am I on, and what can I do here
 *   StatCard     one number, tinted by what kind of number it is
 *   SectionCard  a titled group with an optional "View all" way out
 *   Chips        one-of-many filter, each with its count
 *   AvatarInitials, IconTile, ProgressBar, SearchBox, Segmented
 *
 * Presentation only. Nothing here fetches, decides or stores.
 */



export function IconTile({ icon: Icon, tone = 'neutral', size = 44, iconSize = 20, className = '' }) {
  return (
    <span className={`at-tile at-tile--${tone} ${className}`} style={{ width: size, height: size }}>
      {Icon && <Icon size={iconSize} />}
    </span>
  );
}

export function StatCard({ icon, label, value, sub, tone = 'neutral', onClick, trailing }) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`at-stat at-stat--${tone}${onClick ? ' at-stat--tap' : ''}`}
    >
      {icon && <IconTile icon={icon} tone={tone} />}
      <span className="at-stat-body">
        <span className="at-stat-label">{label}</span>
        <span className="at-stat-value">{value}</span>
        {sub != null && sub !== '' && <span className="at-stat-sub">{sub}</span>}
      </span>
      {trailing && <span className="at-stat-trailing">{trailing}</span>}
    </Tag>
  );
}

export function SectionCard({ icon, tone = 'neutral', title, subtitle, action, actionLabel, children, className = '', style }) {
  return (
    <section className={`at-section ${className}`} style={style}>
      {(title || action) && (
        <header className="at-section-head">
          <div className="at-section-heading">
            {icon && <IconTile icon={icon} tone={tone} size={38} iconSize={18} />}
            <div>
              <div className="at-section-title">{title}</div>
              {subtitle && <div className="at-section-sub">{subtitle}</div>}
            </div>
          </div>
          {action && (
            <button type="button" className="at-link" onClick={action}>
              {actionLabel || 'View all'} <ArrowRight size={14} />
            </button>
          )}
        </header>
      )}
      {children}
    </section>
  );
}

export function Chips({ options, value, onChange }) {
  return (
    <div className="at-chips" role="group">
      {options.map(({ key, label, count }) => (
        <button
          key={key}
          type="button"
          className={`at-chip${value === key ? ' at-chip--active' : ''}`}
          aria-pressed={value === key}
          onClick={() => onChange(key)}
        >
          {label}
          {count != null && <span className="at-chip-count">{count}</span>}
        </button>
      ))}
    </div>
  );
}

const AVATAR_TONES = ['green', 'amber', 'violet', 'blue', 'rose'];

export function AvatarInitials({ name, size = 40, tone }) {
  const initials = String(name || '?')
    .split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?';
  const hue = tone || AVATAR_TONES[[...String(name || '')].reduce((n, c) => n + c.charCodeAt(0), 0) % AVATAR_TONES.length];
  return (
    <span className={`at-avatar at-tile--${hue}`} style={{ width: size, height: size, fontSize: Math.round(size * 0.36) }} aria-hidden="true">
      {initials}
    </span>
  );
}

export function ProgressBar({ pct, tone = 'green' }) {
  const width = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <span className="at-progress" role="progressbar" aria-valuenow={width} aria-valuemin={0} aria-valuemax={100}>
      <i className={`at-progress-fill at-progress-fill--${tone}`} style={{ width: `${width}%` }} />
    </span>
  );
}

export function SearchBox({ value, onChange, placeholder, style }) {
  return (
    <label className="at-search" style={style}>
      <Search size={15} />
      <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
    </label>
  );
}

export function Segmented({ options, value, onChange, ariaLabel }) {
  return (
    <div className="at-seg" role="group" aria-label={ariaLabel}>
      {options.map(({ key, label, icon: Icon }) => (
        <button key={key} type="button" aria-pressed={value === key} onClick={() => onChange(key)}>
          {Icon && <Icon size={14} />}{label}
        </button>
      ))}
    </div>
  );
}

export function PageHeader({ icon: Icon, tone = 'neutral', title, subtitle, actions, aside, meta }) {
  return (
    <header className="at-page-head">
      <div className="at-page-head-left">
        {Icon && <span className={`at-page-icon at-tile at-tile--${tone}`}><Icon size={26} strokeWidth={1.6} /></span>}
        <div className="at-page-head-text">
          <h1 className="at-page-title">{title}</h1>
          {subtitle && <p className="at-page-sub">{subtitle}</p>}
          {meta && <div className="at-page-meta">{meta}</div>}
        </div>
      </div>
      <div className="at-page-head-right">
        {aside && <div className="at-page-aside">{aside}</div>}
        {actions && <div className="at-page-actions">{actions}</div>}
      </div>
    </header>
  );
}

/* ------------------------------------------------------------------ */
/* Dialogs and forms                                                   */
/* ------------------------------------------------------------------ */

/**
 * A dialog with the same anatomy everywhere: a round icon, a serif title, a
 * one-line purpose, a close button; a scrolling body; a footer with the
 * actions. `width` is the card's maximum; on a phone it becomes a sheet.
 */
export function FormModal({ icon: Icon, tone = 'green', title, subtitle, onClose, children, footer, width = '640px', zIndex = 1200, bodyClassName = '' }) {
  return (
    <div className="at-modal-overlay" style={{ zIndex }} onClick={onClose}>
      <div className="at-modal" style={{ maxWidth: width }} role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined}
           onClick={(e) => e.stopPropagation()}>
        <header className="at-modal-head">
          {Icon && <span className={`at-modal-icon at-tile at-tile--${tone}`}><Icon size={26} strokeWidth={1.6} /></span>}
          <div className="at-modal-heading">
            <h3 className="at-modal-title">{title}</h3>
            {subtitle && <p className="at-modal-sub">{subtitle}</p>}
          </div>
          {onClose && (
            <button type="button" className="at-modal-close" onClick={onClose} aria-label="Close">
              <CloseIcon size={18} />
            </button>
          )}
        </header>
        <div className={`at-modal-body ${bodyClassName}`}>{children}</div>
        {footer && <footer className="at-modal-foot">{footer}</footer>}
      </div>
    </div>
  );
}

/** A label, the control, and the small print under it. `icon` puts a tinted
 *  box on the left of the control, the way the forms read. */
export function Field({ label, required, optional, hint, icon: Icon, children, htmlFor, style, className = '' }) {
  return (
    <div className={`at-field ${className}`} style={style}>
      {label && (
        <label className="at-field-label" htmlFor={htmlFor}>
          {label}
          {required && <span className="at-field-req" aria-hidden="true"> *</span>}
          {optional && <span className="at-field-opt"> (Optional)</span>}
        </label>
      )}
      <div className={`at-field-control${Icon ? ' at-field-control--icon' : ''}`}>
        {Icon && <span className="at-field-icon"><Icon size={17} /></span>}
        {children}
      </div>
      {hint && <div className="at-field-hint">{hint}</div>}
    </div>
  );
}

/**
 * A drop area for files, with the two ways a phone actually adds a photo --
 * the gallery and the camera. Dropped or chosen files reach `onFiles` as an
 * array; the inputs reset themselves so the same file can be picked twice.
 */
export function Dropzone({ onFiles, accept = 'image/*', multiple = false, camera = false, title, subtitle, chooseLabel = 'Choose file', cameraLabel = 'Take photo', hint, compact = false, icon: Icon = UploadIcon }) {
  const [over, setOver] = useState(false);
  const fileRef = useRef(null);
  const camRef = useRef(null);
  const take = (list) => {
    const files = [...(list || [])].filter(Boolean);
    if (files.length) onFiles(multiple ? files : files.slice(0, 1));
  };
  return (
    <div
      className={`at-drop${over ? ' at-drop--over' : ''}${compact ? ' at-drop--compact' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files); }}
    >
      <span className="at-drop-icon"><Icon size={compact ? 22 : 30} strokeWidth={1.5} /></span>
      <div className="at-drop-title">{title || (multiple ? 'Drag & drop photos here' : 'Drag & drop a file here')}</div>
      {subtitle !== null && <div className="at-drop-sub">{subtitle || (camera ? 'or choose an option' : 'or choose from your device')}</div>}
      <div className="at-drop-actions">
        {camera && (
          <button type="button" className="btn-secondary at-btn-sm" onClick={() => camRef.current?.click()}>
            <CameraIcon size={14} /> {cameraLabel}
          </button>
        )}
        <button type="button" className="btn-secondary at-btn-sm" onClick={() => fileRef.current?.click()}>
          <UploadIcon size={14} /> {chooseLabel}
        </button>
      </div>
      {hint && <div className="at-drop-hint">{hint}</div>}
      <input ref={fileRef} type="file" accept={accept} multiple={multiple} hidden
             onChange={(e) => { take(e.target.files); e.target.value = ''; }} />
      {camera && (
        <input ref={camRef} type="file" accept="image/*" capture="environment" hidden
               onChange={(e) => { take(e.target.files); e.target.value = ''; }} />
      )}
    </div>
  );
}

/** One chosen photograph, with its remove button and an optional corner label. */
export function PhotoTile({ src, alt = '', onRemove, label, size = 96 }) {
  return (
    <span className="at-photo" style={{ width: size, height: Math.round(size * 1.25) }}>
      <img src={src} alt={alt} />
      {onRemove && (
        <button type="button" className="at-photo-remove" onClick={onRemove} aria-label="Remove photo">
          <CloseIcon size={12} />
        </button>
      )}
      {label && <span className="at-photo-label">{label}</span>}
    </span>
  );
}

export function AddMoreTile({ onClick, hint, size = 96 }) {
  return (
    <button type="button" className="at-photo at-photo--add" style={{ width: size, height: Math.round(size * 1.25) }} onClick={onClick}>
      <span className="at-photo-plus"><PlusIcon size={18} /></span>
      <span className="at-photo-add-text">Add More</span>
      {hint && <span className="at-photo-add-hint">{hint}</span>}
    </button>
  );
}

/** A quiet note beside or below a form: a tip, a rule, a checklist. */
export function InfoNote({ icon: Icon = LightbulbIcon, tone = 'amber', title, children, items, onDismiss, style }) {
  return (
    <div className={`at-note at-note--${tone}`} style={style}>
      <span className="at-note-icon"><Icon size={20} strokeWidth={1.7} /></span>
      <div className="at-note-body">
        {title && <div className="at-note-title">{title}</div>}
        {children && <div className="at-note-text">{children}</div>}
        {items && (
          <ul className="at-note-list">
            {items.map((item) => <li key={item}><CheckIcon size={14} /> {item}</li>)}
          </ul>
        )}
      </div>
      {onDismiss && (
        <button type="button" className="at-modal-close" style={{ width: 28, height: 28 }} onClick={onDismiss} aria-label="Dismiss">
          <CloseIcon size={14} />
        </button>
      )}
    </div>
  );
}

/** A titled group inside a dialog: icon, serif title, gloss, then the fields. */
export function FormSection({ icon: Icon, tone = 'green', title, subtitle, aside, children, className = '', style }) {
  return (
    <section className={`at-form-section ${className}`} style={style}>
      <header className="at-form-section-head">
        {Icon && <IconTile icon={Icon} tone={tone} size={40} iconSize={18} />}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="at-section-title">{title}</div>
          {subtitle && <div className="at-section-sub">{subtitle}</div>}
        </div>
        {aside && <div className="at-form-section-aside">{aside}</div>}
      </header>
      {children}
    </section>
  );
}
