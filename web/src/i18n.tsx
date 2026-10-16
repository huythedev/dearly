import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import vi from './vi.json';

type Language = 'en' | 'vi';
type Appearance = 'system' | 'light' | 'dark';
const Context = createContext({
  language: 'en' as Language, setLanguage: (_value: Language) => {},
  appearance: 'system' as Appearance, setAppearance: (_value: Appearance) => {},
  t: (source: string) => source, date: (seconds: number) => String(seconds),
});
export const useI18n = () => useContext(Context);

export function Preferences({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() => localStorage.getItem('dearly.language') === 'vi' ? 'vi' : 'en');
  const [appearance, setAppearance] = useState<Appearance>(() => {
    const saved = localStorage.getItem('dearly.appearance');
    return saved === 'light' || saved === 'dark' ? saved : 'system';
  });
  useEffect(() => {
    localStorage.setItem('dearly.language', language); document.documentElement.lang = language;
  }, [language]);
  useEffect(() => {
    localStorage.setItem('dearly.appearance', appearance);
    const media = matchMedia('(prefers-color-scheme: dark)');
    const update = () => { document.documentElement.dataset.theme = appearance === 'system' ? (media.matches ? 'dark' : 'light') : appearance; };
    update(); media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [appearance]);
  const t = (source: string) => language === 'vi' ? (vi as Record<string, string>)[source] ?? source : source;
  const date = (seconds: number) => new Date((seconds + 978307200) * 1000).toLocaleDateString(language === 'vi' ? 'vi-VN' : 'en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  return <Context value={{ language, setLanguage, appearance, setAppearance, t, date }}>{children}</Context>;
}
