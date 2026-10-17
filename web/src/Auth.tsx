import { useState, type FormEvent } from 'react';
import { ArrowRight, HeartHandshake, Leaf, LoaderCircle, ShieldCheck, Sprout } from 'lucide-react';
import { Brand, GardenArt } from './components';
import { PreferenceControls } from './PreferenceControls';
import { useI18n } from './i18n';
import type { Dearly } from './useDearly';

export function Auth({ store }: { store: Dearly }) {
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
          {signup && <><label>{t('Date of birth')}<input type="date" name="birthDate" required autoComplete="bday" max={new Date().toISOString().slice(0, 10)} /></label><p className="field-help">{t('You must be 16 or older. A moderator or administrator verifies your age before companion matching is available.')}</p></>}
          <button className="button primary full" disabled={store.busy}>{store.busy ? <LoaderCircle className="spin" size={18} /> : <>{t(signup ? 'Create your space' : 'Come on in')}<ArrowRight size={18} /></>}</button>
        </form>
        <div className="auth-footnote"><Sprout size={17} /><span>{t('No pressure to have the right words. Just be you.')}</span></div>
      </section>
    </main><footer className="auth-footer"><span>© {new Date().getFullYear()} Dearly</span><span>{t('A space for companionship, not a therapy service.')}</span></footer>
  </div>;
}

