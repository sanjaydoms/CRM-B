import { createContext, useContext, useState } from 'react';
import en from './locales/en.js';
import hi from './locales/hi.js';


const dictionaries = { en, hi };
const STORAGE_KEY = 'app_language';

const LanguageContext = createContext();

export const LanguageProvider = ({ children }) => {
  const [language, setLanguageState] = useState(() => {
    return localStorage.getItem(STORAGE_KEY) || 'en';
  });

  const setLanguage = (lang) => {
    if (dictionaries[lang]) {
      setLanguageState(lang);
      localStorage.setItem(STORAGE_KEY, lang);
    }
  };

  /**
   * Helper function to get translation string by dot-notation key
   * e.g. t('dashboard.title') or t('dashboard.welcome', { name: 'Aditi' })
   */
  const t = (keyPath, params = {}) => {
    const keys = keyPath.split('.');
    
    // Primary dictionary lookup
    let current = dictionaries[language];
    for (const key of keys) {
      if (current && current[key] !== undefined) {
        current = current[key];
      } else {
        current = null;
        break;
      }
    }

    // Fallback to English if missing in selected language
    if (current === null && language !== 'en') {
      let fallback = dictionaries.en;
      for (const key of keys) {
        if (fallback && fallback[key] !== undefined) {
          fallback = fallback[key];
        } else {
          fallback = null;
          break;
        }
      }
      current = fallback;
    }

    // If string still not found, return key path
    if (typeof current !== 'string') {
      return keyPath;
    }

    // Replace dynamic parameters e.g. {name}
    let result = current;
    Object.keys(params).forEach((paramKey) => {
      result = result.replace(new RegExp(`\\{${paramKey}\\}`, 'g'), params[paramKey]);
    });

    return result;
  };

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
};

export default LanguageContext;
