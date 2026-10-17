import { useState, type FormEvent } from 'react';
import { ArrowRight, BookOpen, Check, Feather, LockKeyhole, Plus, Search, ShieldCheck, Users } from 'lucide-react';
import { Dialog, Empty } from './components';
import { useI18n } from './i18n';
import { usePage } from './usePage';
import type { Dearly } from './useDearly';
import { activeConnection, audienceLabels, mergeByID, supportLabels, type Audience, type Journal, type Support } from './types';

export function JournalPage({ store }: { store: Dearly }) {
  const { t, date } = useI18n();
  const state = store.envelope!.state;
  const me = state.profiles.find(p => p.id === state.currentUserID)!;
  const page = usePage<Journal>('journals?limit=40', store.setError);
  const [editing, setEditing] = useState<Journal | 'new' | null>(null);
  const [deleting, setDeleting] = useState<Journal | null>(null);
  const [search, setSearch] = useState('');
  const own = mergeByID(page.items, state.journals.filter(j => j.authorID === me.id)).sort((a, b) => b.date - a.date || b.id.localeCompare(a.id));
  const filtered = own.filter(j => `${j.title} ${j.body}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const save = async (payload: Record<string, unknown>) => {
    if (await store.act('journal.save', payload)) { setEditing(null); await page.reload(); }
  };
  return <>
    <div className="page-heading heading-with-action"><div><span className="eyebrow">{t('A MOMENT FOR YOURSELF')}</span><h1>{t('Make room for your thoughts.')}<span className="heading-flower">✳</span></h1><p>{t('The messy, the lovely, the still figuring it out. It all belongs here.')}</p></div><button data-guide="compose" className="button primary" onClick={() => setEditing('new')}><Plus size={18} />{t('New entry')}</button></div>
    <section className="journal-banner"><div><span className="eyebrow">{t('A GENTLE REMINDER')}</span><h2>{t('You can start with one sentence.')}</h2><p>{t('What has been taking up a little space in your mind today?')}</p><button className="text-link" onClick={() => setEditing('new')}>{t('Let it out')}<ArrowRight size={16} /></button></div><div className="banner-flower" aria-hidden="true"><span>✳</span><Feather size={50} strokeWidth={1} /></div></section>
    <div className="section-heading"><div><h2>{t('Your pages')}</h2><p>{t('A collection of moments, in your own words.')}</p></div><span className="privacy-note"><LockKeyhole size={14} />{t('Private unless you choose to share')}</span></div>
    <label data-guide="pages" className="search-box"><Search size={18} /><input value={search} onChange={e => setSearch(e.target.value)} placeholder={t('Find a thought…')} aria-label={t('Search your journal')} /></label>
    {!filtered.length ? <Empty icon={<BookOpen size={26} />} title={search ? 'No matching entries.' : 'Your story starts here.'} action={!search && <button className="button secondary" onClick={() => setEditing('new')}>{t('Write your first entry')}<Feather size={16} /></button>}>{t(search ? 'Try a different word.' : 'A thought, a feeling, a tiny win. There is no wrong place to begin.')}</Empty> : <div className="journal-grid">{filtered.map((entry, index) => <article className={`journal-card paper-${index % 3}`} key={entry.id}>
      <div className="entry-meta"><span>{date(entry.date)}</span><span className="mini-flower" aria-hidden="true">{['✳', '✧', '❋'][index % 3]}</span></div>
      <button className="entry-open" disabled={entry.locked} onClick={() => setEditing(entry)}><h3>{entry.title || t('Untitled thought')}</h3><p>{entry.locked ? t(entry.body) : entry.body}</p></button>
      <div className="entry-footer"><span className="badge">{entry.audience === 'privateOnly' ? <LockKeyhole size={12} /> : <Users size={12} />}{t(audienceLabels[entry.audience])}</span><button className="text-link muted" disabled={store.busy} onClick={() => setDeleting(entry)}>{t('Delete')}</button></div>
      {entry.moderationHidden && <small className="restricted">{t('Sharing restricted by staff. Private edits are available.')}</small>}
    </article>)}</div>}
    {page.cursor && <div className="load-more"><button className="button secondary" disabled={page.loading} onClick={page.more}>{t(page.loading ? 'Loading…' : 'Older entries')}</button></div>}
    <p className="quiet-note"><ShieldCheck size={15} />{t('Your words are yours. You decide what to share, and with whom.')}</p>
    {editing && <JournalEditor entry={editing === 'new' ? null : editing} hasCompanion={Boolean(activeConnection(state))} busy={store.busy} save={save} close={() => setEditing(null)} />}
    {deleting && <Dialog title="Delete this entry?" close={() => setDeleting(null)}><p>{t('The entry and its community responses will be permanently removed.')}</p><div className="dialog-actions"><button className="button secondary" onClick={() => setDeleting(null)}>{t('Keep entry')}</button><button className="button danger" disabled={store.busy} onClick={async () => { if (await store.act('journal.delete', { id: deleting.id })) { setDeleting(null); await page.reload(); } }}>{t('Delete entry')}</button></div></Dialog>}
  </>;
}

function JournalEditor({ entry, hasCompanion, busy, save, close }: { entry: Journal | null; hasCompanion: boolean; busy: boolean; save: (payload: Record<string, unknown>) => Promise<void>; close: () => void }) {
  const { t } = useI18n();
  const [title, setTitle] = useState(entry?.title ?? '');
  const [body, setBody] = useState(entry?.body ?? '');
  const [audience, setAudience] = useState<Audience>(entry?.audience ?? 'privateOnly');
  const [whole, setWhole] = useState(!entry?.sharedText || entry.sharedText === entry.body);
  const [excerpt, setExcerpt] = useState(entry?.sharedText ?? '');
  const [anonymous, setAnonymous] = useState(entry?.anonymous ?? true);
  const [comments, setComments] = useState(entry?.commentsEnabled ?? true);
  const [support, setSupport] = useState<Support>(entry?.support ?? 'listen');
  const [invalid, setInvalid] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const sharedText = audience === 'privateOnly' ? '' : (whole ? body.trim() : excerpt.trim());
    if (audience !== 'privateOnly' && (!sharedText || !body.includes(sharedText))) { setInvalid(t('The shared passage must be part of your journal entry.')); return; }
    await save({ ...(entry ? { id: entry.id } : {}), title, body, sharedText, audience, anonymous, commentsEnabled: comments, support });
  };
  return <Dialog title={entry ? 'A page from your journal' : 'A little space for your thoughts'} close={close}><form onSubmit={submit}>
    <label>{t('Title')}<input value={title} onChange={e => setTitle(e.target.value)} maxLength={160} placeholder={t('Give this moment a name (optional)')} /></label>
    <label>{t('Your words')}<textarea className="writing-area" value={body} onChange={e => setBody(e.target.value)} required maxLength={20000} rows={8} placeholder={t('Start anywhere. No one is grading this.')} /></label>
    <small className="character-count">{body.length.toLocaleString()} / 20,000</small>
    <div className="sharing-settings"><label>{t('Who can read this?')}<select value={audience} disabled={entry?.moderationHidden} onChange={e => setAudience(e.target.value as Audience)}><option value="privateOnly">{t('Only me')}</option><option value="companion" disabled={!hasCompanion}>{t('Companion')}</option><option value="community">{t('Community')}</option></select></label>
      {entry?.moderationHidden && <p className="field-help">{t('Sharing restricted by staff. Private edits are available.')}</p>}
      {audience !== 'privateOnly' && <><label className="check-label"><input type="checkbox" checked={whole} onChange={e => setWhole(e.target.checked)} />{t('Share the entire entry')}</label>{!whole && <label>{t('Passage to share')}<textarea value={excerpt} onChange={e => setExcerpt(e.target.value)} required rows={3} maxLength={20000} /><small>{t('Copy a passage from your entry. The rest stays private.')}</small></label>}
        <label>{t('What would help right now?')}<select value={support} onChange={e => setSupport(e.target.value as Support)}>{Object.entries(supportLabels).map(([key, title]) => <option key={key} value={key}>{t(title)}</option>)}</select></label>
        {audience === 'community' && <><label className="check-label"><input type="checkbox" checked={anonymous} onChange={e => setAnonymous(e.target.checked)} />{t('Post anonymously')}</label><p className="field-help">{t('Anonymous stories do not accept companion invitations. Avoid identifying details in your writing.')}</p><label className="check-label"><input type="checkbox" checked={comments} onChange={e => setComments(e.target.checked)} />{t('Welcome community responses')}</label></>}
        <div className="share-preview"><span className="eyebrow">{t('SHARING PREVIEW')}</span><p>{whole ? body || t('Your shared words will appear here.') : excerpt || t('Your shared words will appear here.')}</p><small>{t('Only this passage will be visible to your chosen audience.')}</small></div>
      </>}
    </div>{invalid && <p role="alert" className="form-error">{invalid}</p>}
    <div className="dialog-actions"><button type="button" className="button secondary" onClick={close}>{t('Close')}</button><button className="button primary" disabled={busy}><Check size={17} />{t(audience === 'privateOnly' ? 'Save privately' : 'Save & share')}</button></div>
  </form></Dialog>;
}
