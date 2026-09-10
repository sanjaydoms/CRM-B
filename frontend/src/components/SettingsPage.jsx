import { useLanguage } from '../i18n/LanguageContext.jsx';
import LanguageSelector from './LanguageSelector.jsx';
import { Globe, ShieldCheck, Building, User, Clock, Info } from 'lucide-react';

// Was a generic SaaS settings page on its own palette (indigo/green/amber
// pastel chips, blue notice, non-existent --bg-primary/--bg-secondary vars).
// Reskinned onto the atelier design system: it rides the shared primitives
// (.ui-card / .ui-section-title / .ui-section-sub / .ui-row / .ui-badge) so it
// cannot drift from the rest of the app, with only genuinely-local overrides
// (the brass icon chip, the resting well on the info rows) inline.
const iconChip = {
  width: '40px', height: '40px', borderRadius: 'var(--radius-md)', flexShrink: 0,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  background: 'var(--accent-color)', color: 'var(--accent-text)',
};

// A static (non-tappable) .ui-row needs a resting fill; the primitive is
// transparent until --tap hover.
const infoRow = { background: 'var(--surface-inset)' };
const infoRowLabel = {
  display: 'flex', alignItems: 'center', gap: '10px',
  fontSize: 'var(--text-sm)', color: 'var(--text-secondary)',
};
const infoRowValue = { fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' };

export const SettingsPage = ({ currentUser, boutiqueSettings }) => {
  const { t } = useLanguage();

  return (
    <div className="settings-page-wrapper" style={{ maxWidth: '1100px', margin: '0 auto' }}>
      <header className="portal-header">
        <div className="portal-header-left">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 'var(--text-3xl)', fontWeight: 400, lineHeight: 'var(--leading-tight)', color: 'var(--text-primary)' }}>
              {t('settingsPage.title')}
            </h1>
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
              {t('settingsPage.subtitle')}
            </p>
          </div>
        </div>
      </header>

      <div
        className="settings-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: 'var(--space-5)',
          marginTop: 'var(--space-6)',
        }}
      >
        {/* Language & Regional Settings Card */}
        <div className="settings-card ui-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={iconChip}><Globe size={18} /></div>
            <div>
              <h2 className="ui-section-title">{t('settingsPage.languageSectionTitle')}</h2>
              <p className="ui-section-sub">{t('settingsPage.languageSectionDesc')}</p>
            </div>
          </div>

          <div style={{ marginTop: '20px', padding: '16px', background: 'var(--surface-inset)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
            <div className="ui-eyebrow" style={{ marginBottom: '10px' }}>
              {t('settingsPage.selectLanguageLabel')}
            </div>
            <LanguageSelector />
          </div>
        </div>

        {/* Workspace & System Info Card */}
        <div className="settings-card ui-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={iconChip}><ShieldCheck size={18} /></div>
            <div>
              <h2 className="ui-section-title">{t('settingsPage.systemSectionTitle')}</h2>
              <p className="ui-section-sub">{t('settingsPage.systemSectionDesc')}</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '20px' }}>
            <div className="ui-row" style={infoRow}>
              <span style={infoRowLabel}><User size={16} /> {t('settingsPage.activeUser')}</span>
              {/* .ui-badge for size/shape; accent fill with forest text — accent-text
                  on the cream fill is only 4.16:1, so the value uses --primary-color. */}
              <span className="ui-badge" style={{ background: 'var(--accent-color)', color: 'var(--primary-color)' }}>
                {currentUser?.role || 'Owner'} ({currentUser?.first_name || currentUser?.email || 'User'})
              </span>
            </div>

            <div className="ui-row" style={infoRow}>
              <span style={infoRowLabel}><Building size={16} /> {t('settingsPage.boutiqueName')}</span>
              <span style={infoRowValue}>{boutiqueSettings?.name || 'Scaleezy Atelier'}</span>
            </div>

            <div className="ui-row" style={infoRow}>
              <span style={infoRowLabel}><Clock size={16} /> {t('settingsPage.timezone')}</span>
              <span style={infoRowValue}>{boutiqueSettings?.timezone || 'Asia/Kolkata (IST)'}</span>
            </div>
          </div>

          <div
            style={{
              marginTop: '24px', padding: '12px 14px', borderRadius: 'var(--radius-md)',
              background: 'var(--info-bg)', border: '1px solid var(--info-color)', color: 'var(--info-color)',
              fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: '8px',
            }}
          >
            <Info size={16} style={{ flexShrink: 0 }} />
            <span>{t('settingsPage.savedNotice')}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;
