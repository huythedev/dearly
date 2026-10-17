import { useState, type FormEvent } from 'react';
import { BookOpen, Check, Leaf, LogOut, ShieldCheck } from 'lucide-react';
import { PreferenceControls } from './PreferenceControls';
import { useI18n } from './i18n';
import { useGuide } from './guide/GuidedTour';
import type { Dearly } from './useDearly';
import { supportLabels, type Profile, type Support } from './types';

export function SettingsPage({ store, me, manage }: { store: Dearly; me: Profile; manage: () => void }) {
  const { t, appearance, setAppearance } = useI18n();
  const [saved, setSaved] = useState(false);
  const guide = useGuide();
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
      <section className="card"><h2>{t('Your account')}</h2><dl className="details"><div><dt>{t('Role')}</dt><dd>{t(store.envelope!.state.currentUserRole ?? 'user')}</dd></div><div><dt>{t('Age verification')}</dt><dd>{t(me.ageVerified ? 'Verified' : 'Awaiting age verification')}</dd></div></dl><p className="field-help">{t('Age verification is required for companion matching. Ask a Dearly moderator or administrator to review your date of birth.')}</p><div className="row-actions wrap account-actions"><button className="button secondary" onClick={() => void store.refresh(true)} disabled={store.busy}>{t('Sync now')}</button>{store.envelope!.state.permissions?.includes('reports.read') && <button className="button secondary" onClick={manage}><ShieldCheck size={15} />{t('Management')}</button>}<button className="text-button" disabled={store.busy} onClick={() => void store.logout()}><LogOut size={15} />{t('Log out')}</button></div></section>
      <section className="card"><h2>{t('A little help getting started')}</h2><p className="field-help">{t('Revisit the main features with a step-by-step guide.')}</p><button type="button" className="button secondary" onClick={guide.start}><BookOpen size={17} />{t('Take a guided tour')}</button></section>
    </div></div></>;
}
