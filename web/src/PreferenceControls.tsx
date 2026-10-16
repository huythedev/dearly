import { Moon, Sun } from 'lucide-react';
import { useI18n } from './i18n';

export function PreferenceControls() {
  const { t, language, setLanguage, isDark, setAppearance } = useI18n();
  return <div className="preference-controls">
    <select aria-label={t('Language')} value={language} onChange={e => setLanguage(e.target.value as 'en' | 'vi')}><option value="en">EN · English</option><option value="vi">VI · Tiếng Việt</option></select>
    <button className="icon-button" title={t(isDark ? 'Light appearance' : 'Dark appearance')} aria-label={t(isDark ? 'Light appearance' : 'Dark appearance')} onClick={() => setAppearance(isDark ? 'light' : 'dark')}>{isDark ? <Sun size={18} /> : <Moon size={18} />}</button>
  </div>;
}

