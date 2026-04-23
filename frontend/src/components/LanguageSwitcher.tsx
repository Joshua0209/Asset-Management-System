import { Segmented } from "antd";
import { useTranslation } from "react-i18next";

import { SUPPORTED_LANGUAGES, type SupportedLanguage } from "../i18n";

const LANGUAGE_LABELS: Record<SupportedLanguage, string> = {
  zh: "中",
  en: "EN",
};

export function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const current = (i18n.resolvedLanguage ?? i18n.language) as SupportedLanguage;

  const handleChange = (lng: SupportedLanguage) => {
    if (lng !== current) {
      i18n.changeLanguage(lng).catch((error) => {
        console.error("Failed to change language:", error);
      });
    }
  };

  const options = SUPPORTED_LANGUAGES.map((lng) => ({
    label: LANGUAGE_LABELS[lng],
    value: lng,
  }));

  return (
    <Segmented
    size="middle"
    options={options}
    value={current}
    onChange={(value) => handleChange(value as SupportedLanguage)}
    />
  );
}
