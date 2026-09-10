import React, { useState } from 'react';
import { useLanguage } from '../i18n/LanguageContext.jsx';
import LanguageSelector from './LanguageSelector.jsx';
import { InvoiceTemplateSelector } from './invoice/InvoiceTemplateSelector.jsx';
import { Globe, ShieldCheck, CheckCircle2, Building, User, Clock, Info, MessageSquare, RotateCw, RefreshCw } from 'lucide-react';
import { api } from '../services/api.js';

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

export const SettingsPage = ({
  currentUser,
  boutiqueSettings,
  whatsappStatus = { connected: false, status: 'disconnected', qrCode: null },
  fetchWhatsAppStatus,
}) => {
  const { t } = useLanguage();
  const [resetting, setResetting] = useState(false);

  React.useEffect(() => {
    if (fetchWhatsAppStatus) {
      fetchWhatsAppStatus();
      const interval = setInterval(fetchWhatsAppStatus, 3000);
      return () => clearInterval(interval);
    }
  }, [fetchWhatsAppStatus]);

  const handleReset = async () => {
    setResetting(true);
    try {
      await api.resetWhatsAppStatus();
      if (fetchWhatsAppStatus) {
        await fetchWhatsAppStatus();
      }
    } catch (err) {
      console.error('Failed to reset WhatsApp session:', err);
    } finally {
      setResetting(false);
    }
  };

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

        {/* WhatsApp Integration & QR Code Card */}
        <div 
          className="settings-card" 
          style={{ 
            backgroundColor: 'var(--bg-primary, #ffffff)', 
            border: '1px solid var(--border-color, #e2e8f0)', 
            borderRadius: '16px', 
            padding: '24px',
            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.04), 0 2px 4px -2px rgba(0,0,0,0.02)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between'
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ padding: '8px', borderRadius: '10px', backgroundColor: '#F0FDF4', color: '#16A34A' }}>
                  <MessageSquare size={20} />
                </div>
                <div>
                  <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary, #0f172a)' }}>
                    {t('settingsPage.whatsappTitle', 'WhatsApp Settings')}
                  </h2>
                  <p style={{ margin: '2px 0 0 0', fontSize: '0.825rem', color: 'var(--text-secondary, #64748b)' }}>
                    {t('settingsPage.whatsappSubtitle', 'Link boutique WhatsApp account')}
                  </p>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '6px', borderRadius: '8px' }}
                  onClick={handleReset}
                  disabled={resetting}
                >
                  <RefreshCw size={13} className={resetting ? 'spin' : ''} />
                  <span>{resetting ? t('settingsPage.resetting', 'Resetting...') : t('settingsPage.resetSession', 'Reset Session')}</span>
                </button>
              </div>
            </div>

            {whatsappStatus.connected ? (
              <div style={{ padding: '16px', background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: '12px', marginTop: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                  <MessageSquare size={18} color="#16A34A" />
                  <span style={{ fontWeight: 600, fontSize: '14px', color: '#166534', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {t('settingsPage.connectedTitle', 'WhatsApp Connected')} <CheckCircle2 size={16} color="#16A34A" />
                  </span>
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary, #475569)', lineHeight: 1.4 }}>
                  {t('settingsPage.connectedDesc', 'Automated customer notifications and stage update messages are active.')}
                </div>
                <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '11px', fontWeight: 600, padding: '4px 10px', background: '#DCFCE7', color: '#15803D', borderRadius: '20px' }}>
                    {t('settingsPage.connectedBadge', 'Connected')}
                  </span>
                  <button
                    type="button"
                    style={{ background: 'none', border: 'none', color: '#EF4444', fontSize: '12px', cursor: 'pointer', textDecoration: 'underline' }}
                    onClick={handleReset}
                  >
                    {t('settingsPage.disconnectRepair', 'Disconnect & Re-pair')}
                  </button>
                </div>
              </div>
            ) : whatsappStatus.qrCode ? (
              <div style={{ padding: '16px', border: '1px solid #25D366', borderRadius: '12px', background: '#FAFFFA', marginTop: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#25D366', fontWeight: 700, fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
                  <MessageSquare size={14} /> {t('settingsPage.linkDevice', 'Link Device')}
                </div>
                <p style={{ margin: '0 0 12px 0', fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  {t('settingsPage.scanQrInstruction', 'Scan with WhatsApp on your mobile phone (Settings > Linked Devices):')}
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '16px', background: '#ffffff', borderRadius: '12px', border: '1px solid #E2E8F0', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
                  <img
                    src={whatsappStatus.qrCode}
                    alt="WhatsApp Link QR Code"
                    style={{ width: '180px', height: '180px', objectFit: 'contain', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '6px', background: '#fff' }}
                  />
                  <div style={{ marginTop: '10px', fontSize: '12px', color: '#16A34A', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <RotateCw size={14} className="spin" /> {t('settingsPage.waitingQrScan', 'Waiting for QR scan...')}
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ padding: '16px', border: '1px dashed #25D366', borderRadius: '12px', background: '#FAFFFA', marginTop: '12px' }}>
                <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                  {t('settingsPage.linkWhatsAppAccount', 'Link WhatsApp Account')}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                  {t('settingsPage.linkWhatsAppDesc', 'Click below to generate WhatsApp QR code for scanning.')}
                </div>
                <button
                  type="button"
                  className="btn-primary"
                  style={{ fontSize: '13px', padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '6px', borderRadius: '8px', width: '100%', justifyContent: 'center', background: '#25D366', border: 'none', color: '#fff', fontWeight: 600, cursor: 'pointer' }}
                  onClick={handleReset}
                  disabled={resetting}
                >
                  <RotateCw size={14} className={resetting ? 'spin' : ''} />
                  <span>{resetting ? t('settingsPage.generatingQrCode', 'Generating QR Code...') : t('settingsPage.generateQrCode', 'Generate WhatsApp QR Code')}</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Invoice Template Selection Card (Right side of WhatsApp Link card) */}
        <InvoiceTemplateSelector currentUser={currentUser} />
      </div>
    </div>
  );
};

export default SettingsPage;
