/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import zh from './locales/zh';
import en from './locales/en';
import { useSettingStore } from './stores/settingStore';

const resources = {
  zh: { translation: zh },
  en: { translation: en },
};

const getInitialLanguage = () => {
  try {
    // directly get language setting from settingStore
    const store = useSettingStore.getState();
    if (store && store.language) {
      return store.language;
    }

    // if store is not set, get language from localStorage
    const storedData = localStorage.getItem('mico-setting-store');
    if (storedData) {
      const parsed = JSON.parse(storedData);
      if (parsed.state && parsed.state.language) {
        return parsed.state.language;
      }
    }

    // finally use browser language
    const browserLang = navigator.language || navigator.userLanguage;
    const langCode = browserLang.split('-')[0];
    const supportedLanguages = ['zh', 'en'];
    return supportedLanguages.includes(langCode) ? langCode : 'zh';
  } catch (error) {
    console.warn('Failed to get initial language:', error);
    return 'zh';
  }
};

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: getInitialLanguage(),
    fallbackLng: 'zh',
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
  });

export default i18n;

