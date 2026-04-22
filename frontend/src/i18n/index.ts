import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import zhTW from "./locales/zh-TW.json";

export const SUPPORTED_LANGUAGES = ["zh-TW", "en"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

const isDev = import.meta.env.DEV;

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      "zh-TW": { translation: zhTW },
      en: { translation: en },
    },
    fallbackLng: "zh-TW",
    supportedLngs: SUPPORTED_LANGUAGES,
    nonExplicitSupportedLngs: true,
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
      lookupLocalStorage: "ams-lang",
    },
    react: {
      useSuspense: false,
    },
    saveMissing: isDev,
    missingKeyHandler: (lngs, ns, key) => {
      if (isDev) {
        console.warn(`[i18n] Missing translation: [${lngs.join(",")}] ${ns}:${key}`);
      }
    },
  });

export default i18n;
