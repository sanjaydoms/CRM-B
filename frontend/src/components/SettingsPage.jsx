import React from 'react';
import { useLanguage } from '../i18n/LanguageContext.jsx';
import LanguageSelector from './LanguageSelector.jsx';
import { Globe, Settings, ShieldCheck, CheckCircle2, Building, User, Clock, Info } from 'lucide-react';

export const SettingsPage = ({ currentUser, boutiqueSettings }) => {
  const { language, setLanguage, t } = useLanguage();

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

          {/* Language Cards Quick Select */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '16px' }}>
            {/* English Card */}
            <div 
              onClick={() => setLanguage('en')}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 16px',
                borderRadius: '12px',
                border: language === 'en' ? '2px solid #4F46E5' : '1px solid var(--border-color, #e2e8f0)',
                backgroundColor: language === 'en' ? '#EEF2FF' : 'var(--bg-primary, #ffffff)',
                cursor: 'pointer',
                transition: 'all 0.2s ease'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '1.25rem' }}>🇬🇧</span>
                <div>
                  <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary, #0f172a)' }}>
                    {t('settingsPage.englishTitle')}
                  </div>
                  <div style={{ fontSize: '0.775rem', color: 'var(--text-secondary, #64748b)' }}>
                    {t('settingsPage.englishDesc')}
                  </div>
                </div>
              </div>
              {language === 'en' && <CheckCircle2 size={18} style={{ color: '#4F46E5' }} />}
            </div>

            {/* Hindi Card */}
            <div 
              onClick={() => setLanguage('hi')}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 16px',
                borderRadius: '12px',
                border: language === 'hi' ? '2px solid #4F46E5' : '1px solid var(--border-color, #e2e8f0)',
                backgroundColor: language === 'hi' ? '#EEF2FF' : 'var(--bg-primary, #ffffff)',
                cursor: 'pointer',
                transition: 'all 0.2s ease'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '1.25rem' }}>🇮🇳</span>
                <div>
                  <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary, #0f172a)' }}>
                    {t('settingsPage.hindiTitle')}
                  </div>
                  <div style={{ fontSize: '0.775rem', color: 'var(--text-secondary, #64748b)' }}>
                    {t('settingsPage.hindiDesc')}
                  </div>
                </div>
              </div>
              {language === 'hi' && <CheckCircle2 size={18} style={{ color: '#4F46E5' }} />}
            </div>

            {/* Telugu Card */}
            <div 
              onClick={() => setLanguage('te')}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 16px',
                borderRadius: '12px',
                border: language === 'te' ? '2px solid #4F46E5' : '1px solid var(--border-color, #e2e8f0)',
                backgroundColor: language === 'te' ? '#EEF2FF' : 'var(--bg-primary, #ffffff)',
                cursor: 'pointer',
                transition: 'all 0.2s ease'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '1.25rem' }}>🇮🇳</span>
                <div>
                  <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary, #0f172a)' }}>
                    {t('settingsPage.teluguTitle', 'తెలుగు (Telugu)')}
                  </div>
                  <div style={{ fontSize: '0.775rem', color: 'var(--text-secondary, #64748b)' }}>
                    {t('settingsPage.teluguDesc', 'తెలుగు ఇంటర్‌ఫేస్ (TE)')}
                  </div>
                </div>
              </div>
              {language === 'te' && <CheckCircle2 size={18} style={{ color: '#4F46E5' }} />}
            </div>
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
      </div>
    </div>
  );
};

export default SettingsPage;
