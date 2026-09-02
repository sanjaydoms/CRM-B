import { createContext, useContext, useState } from 'react';
import en from './locales/en.js';
import hi from './locales/hi.js';
import te from './locales/te.js';
import mr from './locales/mr.js';
import ar from './locales/ar.js';
import gu from './locales/gu.js';
import ml from './locales/ml.js';
import ta from './locales/ta.js';
import kn from './locales/kn.js';
import es from './locales/es.js';
import de from './locales/de.js';


const dictionaries = { en, hi, te, mr, ar, gu, ml, ta, kn, es, de };
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
   * Supports both t('key', { name: 'Aditi' }) and t('key', 'Fallback string', { name: 'Aditi' })
   */
  const t = (keyPath, fallbackOrParams = {}, maybeParams) => {
    let fallbackText = null;
    let params = {};

    if (typeof fallbackOrParams === 'string') {
      fallbackText = fallbackOrParams;
      params = maybeParams && typeof maybeParams === 'object' ? maybeParams : {};
    } else if (fallbackOrParams && typeof fallbackOrParams === 'object') {
      params = fallbackOrParams;
    }

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

    // If string still not found, return fallbackText or keyPath
    if (typeof current !== 'string') {
      current = fallbackText || keyPath;
    }

    // Replace dynamic parameters e.g. {name}
    let result = current;
    if (params && typeof params === 'object') {
      Object.keys(params).forEach((paramKey) => {
        const val = params[paramKey] !== undefined && params[paramKey] !== null ? params[paramKey] : '';
        result = result.replace(new RegExp(`\\{${paramKey}\\}`, 'g'), val);
      });
    }

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
