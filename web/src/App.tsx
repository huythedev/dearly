import { useEffect, useState, type FormEvent } from 'react';
import { createPortal } from 'react-dom';
import { ArrowRight, BookOpen, Check, ChevronRight, CircleHelp, HeartHandshake, Leaf, LoaderCircle, LogOut, MessageCircle, Moon, Settings, ShieldCheck, Sprout, Sun, Users, X } from 'lucide-react';
import { Brand, Avatar, GardenArt } from './components';
import { useI18n } from './i18n';
import { useDearly, type Dearly } from './useDearly';
import { JournalPage, CommunityPage } from './Journals';
import { CompanionPage, GardenPage } from './Companion';
import { StaffPage } from './Staff';
import { supportLabels, type Profile, type Support } from './types';

export function PreferenceControls() {
  const { t, language, setLanguage, appearance, setAppearance } = useI18n();
  const isDark = appearance === 'dark' || (appearance === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
  return <div className="preference-controls">
    <select aria-label={t('Language')} value={language} onChange={e => setLanguage(e.target.value as 'en' | 'vi')}><option value="en">EN · English</option><option value="vi">VI · Tiếng Việt</option></select>
    <button className="icon-button" title={t(isDark ? 'Light appearance' : 'Dark appearance')} aria-label={t(isDark ? 'Light appearance' : 'Dark appearance')} onClick={() => setAppearance(isDark ? 'light' : 'dark')}>{isDark ? <Sun size={18} /> : <Moon size={18} />}</button>
  </div>;
}

function Auth({ store }: { store: Dearly }) {
  const { t } = useI18n();
  const [signup, setSignup] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const fields = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
    await store.authenticate(signup, fields);
  }
  return <div className="auth-page">
    <header className="auth-header"><Brand /><PreferenceControls /></header>
    <main className="auth-main">
      <section className="welcome"><span className="eyebrow"><span className="tiny-star">✳</span> {t('A LITTLE SPACE, JUST FOR YOU')}</span>
        <h1>{t('A softer place')}<br /><em>{t('to land.')}</em></h1>
        <p className="welcome-copy">{t('Some days, you just need to feel heard. Write a little, find a listener, and let something good grow.')}</p>
        <GardenArt stage={3} />
        <div className="welcome-promises"><span><ShieldCheck size={16} />{t('Private by default')}</span><span><HeartHandshake size={16} />{t('Connection at your pace')}</span></div>
      </section>
      <section className="auth-card"><span className="small-icon"><Leaf size={23} /></span><h2>{t(signup ? 'Make yourself at home.' : 'Welcome back.')}</h2><p>{t(signup ? 'A small beginning for a little more connection.' : 'Your quiet corner of the internet is waiting.')}</p>
        <div className="segmented"><button type="button" className={!signup ? 'selected' : ''} onClick={() => { setSignup(false); store.setError(''); }}>{t('Log in')}</button><button type="button" className={signup ? 'selected' : ''} onClick={() => { setSignup(true); store.setError(''); }}>{t('Create account')}</button></div>
        <form onSubmit={submit} key={String(signup)}>
          <label>{t('Username')}<input name="username" required minLength={3} maxLength={64} pattern="[a-zA-Z0-9_.\-]+" autoComplete="username" autoCapitalize="none" spellCheck={false} placeholder={t('Your username')} /></label>
          {signup && <label>{t('Nickname')}<input name="nickname" required maxLength={40} autoComplete="nickname" placeholder={t('What should we call you?')} /></label>}
          <label>{t('Password')}<input type="password" name="password" required minLength={10} maxLength={128} autoComplete={signup ? 'new-password' : 'current-password'} placeholder={t('At least 10 characters')} /></label>
          {signup && <><label>{t('Date of birth')}<input type="date" name="birthDate" required autoComplete="bday" max={new Date().toISOString().slice(0, 10)} /></label><p className="field-help">{t('You must be 16 or older. An administrator verifies your age before companion matching is available.')}</p></>}
          <button className="button primary full" disabled={store.busy}>{store.busy ? <LoaderCircle className="spin" size={18} /> : <>{t(signup ? 'Create your space' : 'Come on in')}<ArrowRight size={18} /></>}</button>
        </form>
        <div className="auth-footnote"><Sprout size={17} /><span>{t('No pressure to have the right words. Just be you.')}</span></div>
      </section>
    </main><footer className="auth-footer"><span>© {new Date().getFullYear()} Dearly</span><span>{t('A space for companionship, not a therapy service.')}</span></footer>
  </div>;
}

type Tab = 'journal' | 'community' | 'companion' | 'garden' | 'settings' | 'management';
const route = () => {
  const path = location.pathname.split('/')[1];
  return (['journal', 'community', 'companion', 'garden', 'settings', 'management'].includes(path) ? path : 'journal') as Tab;
};

export function App() {
  const store = useDearly();
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>(route);
  useEffect(() => { const update = () => setTab(route()); addEventListener('popstate', update); return () => removeEventListener('popstate', update); }, []);
  const navigate = (value: Tab) => { history.pushState({}, '', `/${value}`); setTab(value); window.scrollTo(0, 0); };
  const state = store.envelope?.state;
  const me = state?.profiles.find(p => p.id === state.currentUserID);
  if (store.loading) return <div className="loading-screen"><Brand /><LoaderCircle className="spin" size={24} /><p>{t('Finding your quiet corner…')}</p></div>;
  const links = [
    { id: 'journal' as const, title: 'My journal', subtitle: 'A moment for yourself', icon: BookOpen },
    { id: 'community' as const, title: 'Community', subtitle: 'A little less alone', icon: Users },
    { id: 'companion' as const, title: 'Companion', subtitle: 'Someone to listen', icon: MessageCircle },
    { id: 'garden' as const, title: 'Our garden', subtitle: 'Small acts, growing together', icon: Sprout },
  ];
  return <>
    {state && me ? <div className="app-layout" key={me.id}>
      <aside className="sidebar"><a href="/journal" className="brand-link" onClick={e => { e.preventDefault(); navigate('journal'); }}><Brand /></a>
        <div className="sidebar-caption">{t('YOUR LITTLE CORNER')}</div><nav className="main-nav" aria-label={t('Main navigation')}>
          {links.map(item => <a key={item.id} href={`/${item.id}`} onClick={e => { e.preventDefault(); navigate(item.id); }} className={tab === item.id ? 'active' : ''} aria-current={tab === item.id ? 'page' : undefined}><item.icon size={20} /><span><strong>{t(item.title)}</strong><small>{t(item.subtitle)}</small></span>{tab === item.id && <ChevronRight size={14} />}</a>)}
        </nav>
        <div className="sidebar-note"><span className="tiny-star">✳</span><p>{t('You don’t have to grow all at once.')}</p><span>{t('A little, every day, is enough.')}</span></div>
        <div className="sidebar-bottom">{state.permissions?.includes('reports.read') && <button className={tab === 'management' ? 'text-button active' : 'text-button'} onClick={() => navigate('management')}><ShieldCheck size={17} />{t('Management')}</button>}<button className="text-button" onClick={() => navigate('settings')}><Settings size={17} />{t('Settings')}</button><button className="text-button" disabled={store.busy} onClick={() => void store.logout()}><LogOut size={17} />{t('Log out')}</button><p>{t('A space for companionship.')}<br />{t('Always at your own pace.')}</p></div>
      </aside>
      <div className="app-content"><header className="app-topbar"><div className={`connection-status ${store.syncError ? 'offline' : ''}`} role="status"><span className="status-dot" />{t(store.syncError ? 'Sync interrupted · retrying' : store.chatStatus === 'connected' ? 'A little more connected' : 'Reconnecting chat…')}</div><div className="topbar-actions"><PreferenceControls /><button className="profile-button" onClick={() => navigate('settings')} aria-label={t('Account settings')}><span>{me.nickname}</span><Avatar name={me.nickname} /></button></div></header>
        <main className="page-content" id="main-content">
          {tab === 'journal' && <JournalPage store={store} />}
          {tab === 'community' && <CommunityPage store={store} write={() => navigate('journal')} />}
          {tab === 'companion' && <CompanionPage store={store} />}
          {tab === 'garden' && <GardenPage store={store} find={() => navigate('companion')} />}
          {tab === 'settings' && <SettingsPage store={store} me={me} manage={() => navigate('management')} />}
          {tab === 'management' && (state.permissions?.includes('reports.read') ? <StaffPage store={store} /> : <p>{t('You do not have access to management.')}</p>)}
        </main><footer className="app-footer"><Leaf size={13} />{t('A little space. A little connection. A little growth.')}</footer>
      </div>
    </div> : <Auth store={store} />}
    {store.syncError && !state && <div className="toast" role="alert"><CircleHelp size={18} /><span>{t('Could not reach the server. Check your connection and try again.')}</span><button className="icon-button" onClick={() => void store.refresh(true)} aria-label={t('Try again')}><ArrowRight size={18} /></button></div>}
    {store.error && createPortal(<div className="toast error-toast" role="alert"><CircleHelp size={18} /><span>{t(store.error)}</span><button className="icon-button" aria-label={t('Close')} onClick={() => store.setError('')}><X size={18} /></button></div>, document.querySelector('dialog[open]') ?? document.body)}
  </>;
}

function SettingsPage({ store, me, manage }: { store: Dearly; me: Profile; manage: () => void }) {
  const { t, appearance, setAppearance } = useI18n();
  const [saved, setSaved] = useState(false);
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const okay = await store.act('profile.update', { nickname: form.get('nickname'), bio: form.get('bio'),
      interests: String(form.get('interests')).split(',').map(x => x.trim()).filter(Boolean), support: form.get('support'), pace: form.get('pace') });
    setSaved(okay);
  };
  return <><div className="page-heading"><span className="eyebrow">{t('MAKE YOURSELF AT HOME')}</span><h1>{t('Your space, your pace.')}</h1><p>{t('A few things that make Dearly feel more like you.')}</p></div>
    <div className="settings-grid"><section className="card"><h2>{t('Your profile')}</h2><form onSubmit={save}>
      <label>{t('Nickname')}<input name="nickname" defaultValue={me.nickname} required maxLength={40} /></label>
      <label>{t('A little about you')}<textarea name="bio" defaultValue={me.bio} maxLength={500} rows={3} /></label>
      <label>{t('Interests')}<input name="interests" defaultValue={me.interests.join(', ')} /><small>{t('Up to 8 interests, separated by commas. Keep each under 30 characters.')}</small></label>
      <label>{t('What helps you feel supported?')}<select name="support" defaultValue={me.support}>{Object.entries(supportLabels).map(([value, title]) => <option key={value} value={value as Support}>{t(title)}</option>)}</select></label>
      <label>{t('Your pace')}<input name="pace" defaultValue={me.pace} required maxLength={80} /></label>
      <button className="button primary" disabled={store.busy}>{saved ? <Check size={17} /> : <Leaf size={17} />}{t(saved ? 'Saved' : 'Save profile')}</button>
    </form></section><div className="stack"><section className="card"><h2>{t('Appearance & language')}</h2><label>{t('Appearance')}<select value={appearance} onChange={e => setAppearance(e.target.value as 'system' | 'light' | 'dark')}><option value="system">{t('System')}</option><option value="light">{t('Light')}</option><option value="dark">{t('Dark')}</option></select></label><PreferenceControls /></section>
      <section className="card"><h2>{t('Your account')}</h2><dl className="details"><div><dt>{t('Role')}</dt><dd>{t(store.envelope!.state.currentUserRole ?? 'user')}</dd></div><div><dt>{t('Age verification')}</dt><dd>{t(me.ageVerified ? 'Verified' : 'Awaiting administrator verification')}</dd></div></dl><p className="field-help">{t('Age verification is required for companion matching. Ask your Dearly administrator to review your date of birth.')}</p><div className="row-actions wrap account-actions"><button className="button secondary" onClick={() => void store.refresh(true)} disabled={store.busy}>{t('Sync now')}</button>{store.envelope!.state.permissions?.includes('reports.read') && <button className="button secondary" onClick={manage}><ShieldCheck size={15} />{t('Management')}</button>}<button className="text-button" disabled={store.busy} onClick={() => void store.logout()}><LogOut size={15} />{t('Log out')}</button></div></section>
    </div></div></>;
}
