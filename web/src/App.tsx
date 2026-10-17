import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowRight, BookOpen, ChevronRight, CircleHelp, Leaf, LoaderCircle, LogOut, MessageCircle, Settings, ShieldCheck, Sprout, Users, X } from 'lucide-react';
import { Brand, Avatar } from './components';
import { useI18n } from './i18n';
import { useDearly } from './useDearly';
import { Auth } from './Auth';
import { SettingsPage } from './Settings';
import { PreferenceControls } from './PreferenceControls';
import { JournalPage } from './Journals';
import { CommunityPage } from './Community';
import { CompanionPage, GardenPage } from './Companion';
import { StaffPage } from './Staff';
import { GuidedTour } from './guide/GuidedTour';
import { hasStaffPermission, staffScope } from './permissions';
import { EncryptionNotice } from './Privacy';

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
  const navigate = (value: Tab, replace = false) => { history[replace ? 'replaceState' : 'pushState']({}, '', `/${value}`); setTab(value); window.scrollTo(0, 0); };
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
    {state && me ? <GuidedTour key={me.id} userID={me.id} currentRoute={tab} navigate={value => navigate(value, true)}><div className="app-layout" id="app-shell">
      <aside className="sidebar"><a href="/journal" className="brand-link" onClick={e => { e.preventDefault(); navigate('journal'); }}><Brand /></a>
        <div className="sidebar-caption">{t('YOUR LITTLE CORNER')}</div><nav className="main-nav" aria-label={t('Main navigation')}>
          {links.map(item => <a key={item.id} href={`/${item.id}`} onClick={e => { e.preventDefault(); navigate(item.id); }} className={tab === item.id ? 'active' : ''} aria-current={tab === item.id ? 'page' : undefined}><item.icon size={20} /><span><strong>{t(item.title)}</strong><small>{t(item.subtitle)}</small></span>{tab === item.id && <ChevronRight size={14} />}</a>)}
        </nav>
        <div className="sidebar-note"><span className="tiny-star">✳</span><p>{t('You don’t have to grow all at once.')}</p><span>{t('A little, every day, is enough.')}</span></div>
        <div className="sidebar-bottom">{hasStaffPermission(state, 'reports.read') && <button className={tab === 'management' ? 'text-button active' : 'text-button'} onClick={() => navigate('management')}><ShieldCheck size={17} />{t('Management')}</button>}<button className="text-button" onClick={() => navigate('settings')}><Settings size={17} />{t('Settings')}</button><button className="text-button" disabled={store.busy} onClick={() => void store.logout()}><LogOut size={17} />{t('Log out')}</button><p>{t('A space for companionship.')}<br />{t('Always at your own pace.')}</p></div>
      </aside>
      <div className="app-content"><header className="app-topbar"><div className={`connection-status ${store.syncError ? 'offline' : ''}`} role="status"><span className="status-dot" />{t(store.syncError ? 'Sync interrupted · retrying' : store.chatStatus === 'connected' ? 'A little more connected' : 'Reconnecting chat…')}</div><div className="topbar-actions"><PreferenceControls /><button data-guide="settings" className="profile-button" onClick={() => navigate('settings')} aria-label={t('Account settings')}><span>{me.nickname}</span><Avatar name={me.nickname} /></button></div></header>
        <main className="page-content" id="main-content">
          <EncryptionNotice openSettings={() => navigate('settings')} />
          {tab === 'journal' && <JournalPage store={store} />}
          {tab === 'community' && <CommunityPage store={store} write={() => navigate('journal')} />}
          {tab === 'companion' && <CompanionPage store={store} />}
          {tab === 'garden' && <GardenPage store={store} find={() => navigate('companion')} />}
          {tab === 'settings' && <SettingsPage store={store} me={me} manage={() => navigate('management')} />}
          {tab === 'management' && (hasStaffPermission(state, 'reports.read') ? <StaffPage key={staffScope(state)} store={store} /> : <p>{t('You do not have access to management.')}</p>)}
        </main><footer className="app-footer"><Leaf size={13} />{t('A little space. A little connection. A little growth.')}</footer>
      </div>
    </div></GuidedTour> : <Auth store={store} />}
    {store.syncError && !state && <div className="toast" role="alert"><CircleHelp size={18} /><span>{t('Could not reach the server. Check your connection and try again.')}</span><button className="icon-button" onClick={() => void store.refresh(true)} aria-label={t('Try again')}><ArrowRight size={18} /></button></div>}
    {store.error && createPortal(<div className="toast error-toast" role="alert"><CircleHelp size={18} /><span>{t(store.error)}</span><button className="icon-button" aria-label={t('Close')} onClick={() => store.setError('')}><X size={18} /></button></div>, document.querySelector('dialog[open]') ?? document.body)}
  </>;
}
