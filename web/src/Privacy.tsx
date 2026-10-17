import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from 'react';
import { Download, KeyRound, ShieldCheck, Trash2 } from 'lucide-react';
import { request } from './api';
import { Dialog } from './components';
import { useI18n } from './i18n';
import { activeConnection } from './types';
import type { Dearly } from './useDearly';
import { vault } from './vault';

export function EncryptionNotice({ openSettings }: { openSettings: () => void }) {
  const state = useSyncExternalStore(vault.subscribe, vault.snapshot);
  const { t } = useI18n();
  if (!state.needsBackup && state.status !== 'locked') return null;
  return <div className="encryption-notice" role="note"><KeyRound size={17} /><span>{t(state.status === 'locked'
    ? 'Unlock your encrypted journal and chat with your recovery code.' : 'Save your recovery code to open encrypted content on another device.')}</span>
    <button className="text-link" onClick={openSettings}>{t('Encryption settings')}</button></div>;
}

export function PrivacySettings({ store }: { store: Dearly }) {
  const { t } = useI18n();
  const state = useSyncExternalStore(vault.subscribe, vault.snapshot);
  const [code, setCode] = useState('');
  const [recovery, setRecovery] = useState('');
  const [partnerFingerprint, setPartnerFingerprint] = useState('');
  const [dialog, setDialog] = useState<'export' | 'delete' | null>(null);
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [decrypt, setDecrypt] = useState(true);
  const [busy, setBusy] = useState(false);
  const operation = useRef<AbortController | null>(null);
  const alive = useRef(true);
  const userID = store.envelope!.state.currentUserID;
  const partnerID = activeConnection(store.envelope!.state)?.members.find(id => id !== userID);
  useEffect(() => { alive.current = true; return () => { alive.current = false; operation.current?.abort(); }; }, []);
  const perform = async (action: () => Promise<void>) => {
    setBusy(true); store.setError('');
    try { await action(); } catch (error) { if (alive.current) store.setError(error instanceof Error ? error.message : 'Please try again.'); }
    finally { if (alive.current) setBusy(false); }
  };
  const close = () => { if (!busy) { setDialog(null); setPassword(''); setConfirmation(''); } };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void perform(async () => {
      if (dialog === 'delete') { await store.deleteAccount(password, confirmation); return; }
      const controller = operation.current = new AbortController();
      const data = await request<Record<string, unknown>>('account/export', { method: 'POST', signal: controller.signal,
        headers: { 'X-Dearly-User': userID }, body: JSON.stringify({ password }) });
      const result = await vault.dataExport(data, decrypt && state.status === 'ready');
      if (!alive.current || controller.signal.aborted) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }));
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `dearly-data-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
      setDialog(null); setPassword('');
    });
  };
  return <>
    <section className="card privacy-card"><h2><ShieldCheck size={20} />{t('Encryption & recovery')}</h2>
      <p>{t('New journal text, private titles, companion passages and messages are encrypted on your device. Community passages are public. Older content stays as it was until you edit and save it.')}</p>
      {state.status === 'ready' ? <>
        <p className="badge">{t('Encryption ready')}</p>
        <p className="field-help">{t('Keep your recovery code somewhere safe. You need it on a new browser or iPhone. Dearly cannot recover it for you.')}</p>
        {!code ? <button className="button secondary" disabled={busy} onClick={() => void perform(async () => setCode(await vault.code()))}><KeyRound size={16} />{t('Show recovery code')}</button> : <div className="stack">
          <label>{t('Recovery code')}<textarea className="recovery-code" value={code} readOnly rows={3} spellCheck={false} autoComplete="off" /></label>
          <div className="row-actions wrap"><button className="button secondary" disabled={busy} onClick={() => void perform(async () => { await vault.markBackedUp(); setCode(''); })}>{t('I saved my recovery code')}</button><button className="text-button" onClick={() => setCode('')}>{t('Hide')}</button></div>
        </div>}
      </> : state.status === 'locked' ? <form onSubmit={event => { event.preventDefault(); void perform(async () => { await vault.recover(recovery); setRecovery(''); await store.refresh(true); }); }}>
        <p>{t('This device needs your recovery code. Your account can still use community features while encryption is locked.')}</p>
        <label>{t('Recovery code')}<textarea value={recovery} onChange={e => setRecovery(e.target.value)} required rows={3} maxLength={120} spellCheck={false} autoComplete="off" /></label>
        <button className="button primary" disabled={busy}>{t('Unlock encryption')}</button>
      </form> : <><p role="status">{t(state.error || 'Preparing encryption…')}</p><button className="button secondary" disabled={busy || state.status === 'loading'} onClick={() => void perform(async () => { await vault.retry(userID); await store.refresh(true); })}>{t('Try again')}</button></>}
      {state.fingerprint && <details><summary>{t('Verify encryption keys')}</summary><p>{t('Compare these fingerprints with your companion through another trusted channel. A match helps confirm who holds the keys.')}</p><label>{t('Your fingerprint')}<code className="fingerprint">{state.fingerprint}</code></label>
        {partnerID && <><button className="text-link" disabled={busy} onClick={() => void perform(async () => setPartnerFingerprint((await vault.peer(partnerID)).fingerprint))}>{t('Show companion fingerprint')}</button>{partnerFingerprint && <code className="fingerprint">{partnerFingerprint}</code>}</>}
      </details>}
    </section>
    <section className="card privacy-card"><h2>{t('Your data')}</h2><p>{t('Download the content you created and your account details, or permanently delete your account. Both require your current password.')}</p>
      <div className="row-actions wrap"><button className="button secondary" onClick={() => { setDecrypt(state.status === 'ready'); setDialog('export'); }}><Download size={16} />{t('Download my data')}</button><button className="text-button danger-text" onClick={() => setDialog('delete')}><Trash2 size={16} />{t('Delete my account')}</button></div>
    </section>
    {dialog && <Dialog title={dialog === 'export' ? 'Download your data' : 'Permanently delete your account?'} close={close}><form onSubmit={submit}>
      <p>{t(dialog === 'export' ? 'Your file includes your profile, authored content and connection history. Keep it somewhere private.' : 'Your profile, journals, sent messages and encryption keys will be removed. All sessions will end. This cannot be undone. A deleted-account marker remains in shared garden history.')}</p>
      {dialog === 'export' && <><label className="check-label"><input type="checkbox" checked={decrypt && state.status === 'ready'} disabled={state.status !== 'ready'} onChange={e => setDecrypt(e.target.checked)} />{t('Decrypt content on this device')}</label><p className="field-help">{t(decrypt && state.status === 'ready' ? 'The downloaded file will contain readable private text. Encrypted originals are also included.' : 'Encrypted text stays encrypted in the download. Keep your recovery code to read it later.')}</p></>}
      <label>{t('Current password')}<input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={10} maxLength={128} autoComplete="current-password" /></label>
      {dialog === 'delete' && <label>{t('Type DELETE to confirm')}<input value={confirmation} onChange={e => setConfirmation(e.target.value)} required pattern="DELETE" autoComplete="off" spellCheck={false} /></label>}
      <div className="dialog-actions"><button type="button" className="button secondary" disabled={busy} onClick={close}>{t('Cancel')}</button><button className={`button ${dialog === 'delete' ? 'danger' : 'primary'}`} disabled={busy || store.busy}>{t(busy ? 'Please wait…' : dialog === 'delete' ? 'Permanently delete' : 'Download data')}</button></div>
    </form></Dialog>}
  </>;
}
