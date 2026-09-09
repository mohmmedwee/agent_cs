import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import ar from './ar.json'
import en from './en.json'

export const LOCALES = ['en', 'ar'] as const
export type Locale = (typeof LOCALES)[number]

const STORAGE_KEY = 'agent-console:locale'

function initialLocale(): Locale {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'en' || saved === 'ar') return saved
  return navigator.language.startsWith('ar') ? 'ar' : 'en'
}

/**
 * Direction lives on <html> rather than a wrapper div so that native widgets —
 * scrollbars, select popups, text selection — flip with the language too.
 */
export function applyLocale(locale: Locale) {
  document.documentElement.lang = locale
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr'
  localStorage.setItem(STORAGE_KEY, locale)
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } },
  lng: initialLocale(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

applyLocale(i18n.language as Locale)

i18n.on('languageChanged', (lng) => applyLocale(lng as Locale))

export default i18n
