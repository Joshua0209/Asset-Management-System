import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import enTranslation from '../locales/en/translation.json';
import zhTWTranslation from '../locales/zh-TW/translation.json';

const resources = {
  en: {
    translation: enTranslation,
  },
  'zh-TW': {
    translation: zhTWTranslation,
  },
};

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: 'zh-TW', // Default language
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false, // React already safes from XSS
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
  });

export default i18n;
