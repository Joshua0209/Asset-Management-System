import { useTranslation } from "react-i18next";

import { SUPPORTED_LANGUAGES, type SupportedLanguage } from "../i18n";

const LANGUAGE_LABELS: Record<SupportedLanguage, string> = {
  "zh-TW": "中",
  en: "EN",
};

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  const current = (i18n.resolvedLanguage ?? i18n.language) as SupportedLanguage;
  const activeIndex = Math.max(0, SUPPORTED_LANGUAGES.indexOf(current));

  const handleChange = (lng: SupportedLanguage) => {
    if (lng !== current) {
      i18n.changeLanguage(lng).catch((error) => {
        console.error("Failed to change language:", error);
      });
    }
  };

  return (
    <fieldset className="lang-switcher">
      <legend className="lang-switcher__legend">{t("common.language.label")}</legend>
      <span
        className="lang-switcher__thumb"
        style={{ transform: `translateX(${activeIndex * 100}%)` }}
        aria-hidden="true"
      />
      {SUPPORTED_LANGUAGES.map((lng) => (
        <button
          key={lng}
          type="button"
          className={`lang-switcher__btn${current === lng ? " is-active" : ""}`}
          onClick={() => handleChange(lng)}
          aria-pressed={current === lng}
        >
          {LANGUAGE_LABELS[lng]}
        </button>
      ))}
    </fieldset>
  );
}
