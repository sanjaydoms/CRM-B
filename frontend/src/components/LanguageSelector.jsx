import { useLanguage } from '../i18n/LanguageContext.jsx';
import { Globe } from 'lucide-react';

export const LanguageSelector = () => {
  const { language, setLanguage } = useLanguage();

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '5px 12px',
        fontSize: '0.85rem',
        fontWeight: 600,
        borderRadius: '20px',
        border: '1px solid var(--border-color, #e2e8f0)',
        backgroundColor: 'var(--bg-secondary, #f8fafc)',
        color: 'var(--text-primary, #0f172a)',
        boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
      }}
    >
      <Globe size={16} style={{ color: '#6366f1', flexShrink: 0 }} />
      <select
        value={language}
        onChange={(e) => setLanguage(e.target.value)}
        aria-label="Select Language"
        style={{
          background: 'transparent',
          border: 'none',
          outline: 'none',
          color: 'var(--text-primary, #0f172a)',
          fontWeight: 600,
          fontSize: '0.85rem',
          cursor: 'pointer',
          paddingRight: '4px',
        }}
      >
        <option value="en">English (ENGLISH)</option>
        <option value="hi">हिंदी (HINDI)</option>
        <option value="te">తెలుగు (TELUGU)</option>
        <option value="mr">मराठी (MARATHI)</option>
        <option value="ar">العربية (ARABIC)</option>
        <option value="gu">ગુજરાતી (GUJARATI)</option>
        <option value="ml">മലയാളം (MALAYALAM)</option>
        <option value="ta">தமிழ் (TAMIL)</option>
        <option value="kn">ಕನ್ನಡ (KANNADA)</option>
        <option value="es">Español (SPANISH)</option>
        <option value="de">German / Deutsch (GERMAN)</option>
      </select>
    </div>
  );
};

export default LanguageSelector;
