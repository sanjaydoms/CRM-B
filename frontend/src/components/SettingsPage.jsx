import React, { useState } from 'react';
import { useLanguage } from '../i18n/LanguageContext.jsx';
import LanguageSelector from './LanguageSelector.jsx';
import { InvoiceTemplateSelector } from './invoice/InvoiceTemplateSelector.jsx';
import { Globe, Settings, ShieldCheck, CheckCircle2, Building, User, Clock, Info, MessageSquare, RotateCw, RefreshCw } from 'lucide-react';
import { api } from '../services/api.js';

export const SettingsPage = ({
  currentUser,
  boutiqueSettings,
  whatsappStatus = { connected: false, status: 'disconnected', qrCode: null },
  fetchWhatsAppStatus,
}) => {
  const { language, setLanguage, t } = useLanguage();
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
    <div className="settings-page-wrapper" style={{ padding: '24px', maxWidth: '1100px', margin: '0 auto' }}>
      {/* Header */}
      <div 
        className="settings-page-header" 
        style={{ 
          marginBottom: '28px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '16px',
          backgroundColor: 'var(--bg-secondary, #fafbfc)',
          padding: '24px',
          borderRadius: '16px',
          border: '1px solid var(--border-color, #e2e8f0)',
          boxShadow: '0 2px 4px rgba(0,0,0,0.02)'
        }}
      >
        <div 
          style={{ 
            width: '48px', 
            height: '48px', 
            borderRadius: '12px', 
            backgroundColor: '#EEF2FF', 
            color: '#4F46E5', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            flexShrink: 0
          }}
        >
          <Settings size={24} />
        </div>
        <div>
          <h1 style={{ margin: '0 0 6px 0', fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary, #0f172a)' }}>
            {t('settingsPage.title')}
          </h1>
          <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-secondary, #64748b)', lineHeight: '1.5' }}>
            {t('settingsPage.subtitle')}
          </p>
        </div>
      </div>

      {/* Main Grid */}
      <div 
        className="settings-grid" 
        style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', 
          gap: '24px' 
        }}
      >
        {/* Language & Regional Settings Card */}
        <div 
          className="settings-card" 
          style={{ 
            backgroundColor: 'var(--bg-primary, #ffffff)', 
            border: '1px solid var(--border-color, #e2e8f0)', 
            borderRadius: '16px', 
            padding: '24px',
            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.04), 0 2px 4px -2px rgba(0,0,0,0.02)'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ padding: '8px', borderRadius: '10px', backgroundColor: '#F0FDF4', color: '#16A34A' }}>
              <Globe size={20} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary, #0f172a)' }}>
                {t('settingsPage.languageSectionTitle')}
              </h2>
              <p style={{ margin: '2px 0 0 0', fontSize: '0.825rem', color: 'var(--text-secondary, #64748b)' }}>
                {t('settingsPage.languageSectionDesc')}
              </p>
            </div>
          </div>

          <div style={{ margin: '20px 0', padding: '16px', backgroundColor: 'var(--bg-secondary, #f8fafc)', borderRadius: '12px', border: '1px solid var(--border-color, #e2e8f0)' }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary, #0f172a)', marginBottom: '10px' }}>
              {t('settingsPage.selectLanguageLabel')}
            </div>
            <LanguageSelector />
          </div>
        </div>

        {/* Workspace & System Info Card */}
        <div 
          className="settings-card" 
          style={{ 
            backgroundColor: 'var(--bg-primary, #ffffff)', 
            border: '1px solid var(--border-color, #e2e8f0)', 
            borderRadius: '16px', 
            padding: '24px',
            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.04), 0 2px 4px -2px rgba(0,0,0,0.02)'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ padding: '8px', borderRadius: '10px', backgroundColor: '#FEF3C7', color: '#D97706' }}>
              <ShieldCheck size={20} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary, #0f172a)' }}>
                {t('settingsPage.systemSectionTitle')}
              </h2>
              <p style={{ margin: '2px 0 0 0', fontSize: '0.825rem', color: 'var(--text-secondary, #64748b)' }}>
                {t('settingsPage.systemSectionDesc')}
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', borderRadius: '10px', backgroundColor: 'var(--bg-secondary, #f8fafc)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.85rem', color: 'var(--text-secondary, #64748b)' }}>
                <User size={16} />
                <span>{t('settingsPage.activeUser')}</span>
              </div>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#4F46E5', backgroundColor: '#EEF2FF', padding: '4px 10px', borderRadius: '20px' }}>
                {currentUser?.role || 'Owner'} ({currentUser?.first_name || currentUser?.email || 'User'})
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', borderRadius: '10px', backgroundColor: 'var(--bg-secondary, #f8fafc)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.85rem', color: 'var(--text-secondary, #64748b)' }}>
                <Building size={16} />
                <span>{t('settingsPage.boutiqueName')}</span>
              </div>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary, #0f172a)' }}>
                {boutiqueSettings?.name || 'Scaleezy Atelier'}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', borderRadius: '10px', backgroundColor: 'var(--bg-secondary, #f8fafc)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.85rem', color: 'var(--text-secondary, #64748b)' }}>
                <Clock size={16} />
                <span>{t('settingsPage.timezone')}</span>
              </div>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary, #0f172a)' }}>
                {boutiqueSettings?.timezone || 'Asia/Kolkata (IST)'}
              </span>
            </div>
          </div>

          <div 
            style={{ 
              marginTop: '24px', 
              padding: '12px 14px', 
              borderRadius: '10px', 
              backgroundColor: '#EFF6FF', 
              border: '1px solid #BFDBFE', 
              color: '#1E40AF',
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
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
                    WhatsApp Settings
                  </h2>
                  <p style={{ margin: '2px 0 0 0', fontSize: '0.825rem', color: 'var(--text-secondary, #64748b)' }}>
                    Link boutique WhatsApp account
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
                  <span>{resetting ? 'Resetting...' : 'Reset Session'}</span>
                </button>
              </div>
            </div>

            {whatsappStatus.connected ? (
              <div style={{ padding: '16px', background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: '12px', marginTop: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                  <MessageSquare size={18} color="#16A34A" />
                  <span style={{ fontWeight: 600, fontSize: '14px', color: '#166534', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    WhatsApp Connected <CheckCircle2 size={16} color="#16A34A" />
                  </span>
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary, #475569)', lineHeight: 1.4 }}>
                  Automated customer notifications and stage update messages are active.
                </div>
                <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '11px', fontWeight: 600, padding: '4px 10px', background: '#DCFCE7', color: '#15803D', borderRadius: '20px' }}>
                    Connected
                  </span>
                  <button
                    type="button"
                    style={{ background: 'none', border: 'none', color: '#EF4444', fontSize: '12px', cursor: 'pointer', textDecoration: 'underline' }}
                    onClick={handleReset}
                  >
                    Disconnect & Re-pair
                  </button>
                </div>
              </div>
            ) : whatsappStatus.qrCode ? (
              <div style={{ padding: '16px', border: '1px solid #25D366', borderRadius: '12px', background: '#FAFFFA', marginTop: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#25D366', fontWeight: 700, fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
                  <MessageSquare size={14} /> Link Device
                </div>
                <p style={{ margin: '0 0 12px 0', fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  Scan with WhatsApp on your mobile phone (Settings &gt; Linked Devices):
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '16px', background: '#ffffff', borderRadius: '12px', border: '1px solid #E2E8F0', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
                  <img
                    src={whatsappStatus.qrCode}
                    alt="WhatsApp Link QR Code"
                    style={{ width: '180px', height: '180px', objectFit: 'contain', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '6px', background: '#fff' }}
                  />
                  <div style={{ marginTop: '10px', fontSize: '12px', color: '#16A34A', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <RotateCw size={14} className="spin" /> Waiting for QR scan...
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ padding: '16px', border: '1px dashed #25D366', borderRadius: '12px', background: '#FAFFFA', marginTop: '12px' }}>
                <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                  Link WhatsApp Account
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                  Click below to generate WhatsApp QR code for scanning.
                </div>
                <button
                  type="button"
                  className="btn-primary"
                  style={{ fontSize: '13px', padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '6px', borderRadius: '8px', width: '100%', justifyContent: 'center', background: '#25D366', border: 'none', color: '#fff', fontWeight: 600, cursor: 'pointer' }}
                  onClick={handleReset}
                  disabled={resetting}
                >
                  <RotateCw size={14} className={resetting ? 'spin' : ''} />
                  <span>{resetting ? 'Generating QR Code...' : 'Generate WhatsApp QR Code'}</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Invoice Template Selection Section */}
      <InvoiceTemplateSelector currentUser={currentUser} />
    </div>
  );
};

export default SettingsPage;
