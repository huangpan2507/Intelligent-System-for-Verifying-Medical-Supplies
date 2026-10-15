import { createInstance } from "i18next";
import { useTranslation as useReactTranslation } from "react-i18next";
import en from "@/locales/en.json";
import zh from "@/locales/zh-Hans.json";

export const businessI18n = createInstance();
void businessI18n.init({
  resources: { en: { translation: en }, "zh-Hans": { translation: zh } },
  lng: "zh-Hans",
  fallbackLng: "en",
  initImmediate: false,
  keySeparator: false,
  interpolation: { escapeValue: false },
});

// Scope Chinese presentation to Business without changing the global language.
export const useTranslation = () =>
  useReactTranslation(undefined, { i18n: businessI18n });
export const businessText = businessI18n.getFixedT("zh-Hans");
// Selector captions preserve their original English presentation. Source values
// (field names, connection names, categories, paths and expressions) stay verbatim.
export const businessOption = businessI18n.getFixedT("en");
