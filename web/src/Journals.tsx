import { useState, type FormEvent } from 'react';
import { ArrowRight, BookOpen, Check, Feather, Flag, Heart, LockKeyhole, MessageCircle, MoreHorizontal, Plus, Search, Send, ShieldCheck, Users } from 'lucide-react';
import { Avatar, Dialog, Empty } from './components';
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
    <div className="page-heading heading-with-action"><div><span className="eyebrow">{t('A MOMENT FOR YOURSELF')}</span><h1>{t('Make room for your thoughts.')}<span className="heading-flower">✳</span></h1><p>{t('The messy, the lovely, the still figuring it out. It all belongs here.')}</p></div><button className="button primary" onClick={() => setEditing('new')}><Plus size={18} />{t('New entry')}</button></div>
    <section className="journal-banner"><div><span className="eyebrow">{t('A GENTLE REMINDER')}</span><h2>{t('You can start with one sentence.')}</h2><p>{t('What has been taking up a little space in your mind today?')}</p><button className="text-link" onClick={() => setEditing('new')}>{t('Let it out')}<ArrowRight size={16} /></button></div><div className="banner-flower" aria-hidden="true"><span>✳</span><Feather size={50} strokeWidth={1} /></div></section>
    <div className="section-heading"><div><h2>{t('Your pages')}</h2><p>{t('A collection of moments, in your own words.')}</p></div><span className="privacy-note"><LockKeyhole size={14} />{t('Private unless you choose to share')}</span></div>
    <label className="search-box"><Search size={18} /><input value={search} onChange={e => setSearch(e.target.value)} placeholder={t('Find a thought…')} aria-label={t('Search your journal')} /></label>
    {!filtered.length ? <Empty icon={<BookOpen size={26} />} title={search ? 'No matching entries.' : 'Your story starts here.'} action={!search && <button className="button secondary" onClick={() => setEditing('new')}>{t('Write your first entry')}<Feather size={16} /></button>}>{t(search ? 'Try a different word.' : 'A thought, a feeling, a tiny win. There is no wrong place to begin.')}</Empty> : <div className="journal-grid">{filtered.map((entry, index) => <article className={`journal-card paper-${index % 3}`} key={entry.id}>
      <div className="entry-meta"><span>{date(entry.date)}</span><span className="mini-flower" aria-hidden="true">{['✳', '✧', '❋'][index % 3]}</span></div>
      <button className="entry-open" onClick={() => setEditing(entry)}><h3>{entry.title || t('Untitled thought')}</h3><p>{entry.body}</p></button>
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

export function CommunityPage({ store, write }: { store: Dearly; write: () => void }) {
  const { t } = useI18n();
  const state = store.envelope!.state;
  const [filter, setFilter] = useState('all');
  const posts = state.journals.filter(j => j.audience === 'community' && (filter === 'all' || j.support === filter)).sort((a, b) => b.date - a.date || b.id.localeCompare(a.id));
  return <><div className="page-heading heading-with-action"><div><span className="eyebrow">{t('A LITTLE LESS ALONE')}</span><h1>{t('There is room for you here.')}</h1><p>{t('Real feelings. Shared gently. Sometimes listening is everything.')}</p></div><button className="button primary" onClick={write}><Feather size={17} />{t('Share a thought')}</button></div>
    <div className="community-layout"><div><div className="filter-chips"><button className={filter === 'all' ? 'chip selected' : 'chip'} onClick={() => setFilter('all')}>{t('All stories')}</button>{Object.entries(supportLabels).map(([key, title]) => <button key={key} className={filter === key ? 'chip selected' : 'chip'} onClick={() => setFilter(key)}>{t(title)}</button>)}</div>
      <div className="stack">{posts.length ? posts.map(post => <CommunityPost key={post.id} store={store} post={post} />) : <Empty icon={<Users size={26} />} title="A quiet moment in the community.">{t('Be the first to share a little of what is on your mind.')}</Empty>}</div><p className="quiet-note">{t('Showing recent stories. Your personal archive is in My journal.')}</p></div>
      <aside className="community-aside card"><span className="small-icon"><Heart size={22} /></span><h2>{t('A little kindness goes a long way.')}</h2><p>{t('Listen before offering advice. Respect the kind of support each writer asks for.')}</p><hr /><ShieldCheck size={20} /><p>{t('Share only what feels right. You can hide or report a story at any time.')}</p></aside></div>
  </>;
}

function CommunityPost({ store, post }: { store: Dearly; post: Journal }) {
  const { t, date } = useI18n();
  const state = store.envelope!.state;
  const own = post.authorID === state.currentUserID;
  const author = state.profiles.find(p => p.id === post.authorID);
  const name = post.anonymous ? t('A friend') : author?.nickname ?? t('A friend');
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [blocking, setBlocking] = useState(false);
  const [text, setText] = useState('');
  const replies = state.comments.filter(c => c.journalID === post.id);
  const send = async (event: FormEvent) => { event.preventDefault(); if (await store.act('journal.comment', { id: post.id, text })) setText(''); };
  return <article className="post card"><header className="post-header"><Avatar name={name} /><div><strong>{name}{own && <span className="muted"> · {t('you')}</span>}</strong><small>{date(post.date)}{post.anonymous && ` · ${t('Anonymous')}`}</small></div>{!own && <button className="icon-button post-menu-button" onClick={() => setMenu(!menu)} aria-label={t('Story actions')} aria-expanded={menu}><MoreHorizontal size={20} /></button>}</header>
    {menu && <div className="post-actions"><button className="text-button" disabled={store.busy} onClick={() => void store.act('journal.hide', { id: post.id })}>{t('Hide this story')}</button><button className="text-button" onClick={() => { setReporting(true); setMenu(false); }}><Flag size={14} />{t('Report story')}</button>{!post.anonymous && <button className="text-button" onClick={() => setBlocking(true)}>{t('Block account')}</button>}</div>}
    <span className="badge support-badge">{t(supportLabels[post.support])}</span><p className="post-body">{post.sharedText}</p>
    <div className="post-footer"><button className={`text-button ${post.listeners.includes(state.currentUserID) ? 'listened' : ''}`} disabled={store.busy || own} onClick={() => void store.act('journal.listen', { id: post.id, enabled: !post.listeners.includes(state.currentUserID) })}><Heart size={17} fill={post.listeners.includes(state.currentUserID) ? 'currentColor' : 'none'} />{t(post.listeners.includes(state.currentUserID) ? 'Listening' : 'I hear you')}</button><button className="text-button" onClick={() => setCommentsOpen(!commentsOpen)}><MessageCircle size={17} />{replies.length} {t('responses')}</button>{!own && post.canInviteAuthor && <button className="text-button" disabled={store.busy} onClick={() => void store.act('invitation.send', { journalID: post.id })}>{t('Invite to connect')}<ArrowRight size={14} /></button>}</div>
    {commentsOpen && <div className="comments"><div className="stack">{replies.map(reply => <div className="comment" key={reply.id}><Avatar name={state.profiles.find(p => p.id === reply.authorID)?.nickname ?? '?'} /><div><strong>{reply.authorID === post.id ? t('A friend') : state.profiles.find(p => p.id === reply.authorID)?.nickname ?? t('A friend')}</strong><p>{reply.text}</p></div></div>)}</div>{post.commentsEnabled ? <form onSubmit={send} className="inline-form"><input value={text} onChange={e => setText(e.target.value)} placeholder={t('Respond with kindness…')} required maxLength={2000} aria-label={t('Your response')} /><button className="icon-button" disabled={store.busy} aria-label={t('Send response')}><Send size={18} /></button></form> : <p className="field-help">{t('Responses are turned off for this story.')}</p>}</div>}
    {reporting && <ReportDialog store={store} payload={{ journalID: post.id }} close={() => setReporting(false)} />}
    {blocking && <Dialog title="Block this account?" close={() => setBlocking(false)}><p>{t('This ends your connection and removes pending invitations with this account.')}</p><div className="dialog-actions"><button className="button secondary" onClick={() => setBlocking(false)}>{t('Cancel')}</button><button className="button danger" disabled={store.busy} onClick={async () => { if (await store.act('user.block', { journalID: post.id })) setBlocking(false); }}>{t('Block account')}</button></div></Dialog>}
  </article>;
}

export function ReportDialog({ store, payload, close }: { store: Dearly; payload: Record<string, unknown>; close: () => void }) {
  const { t } = useI18n();
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const reason = new FormData(event.currentTarget).get('reason');
    if (await store.act('report.create', { ...payload, reason })) close();
  };
  return <Dialog title="Tell us what happened" close={close}><p>{t('Reports go to Dearly moderators for review.')}</p><form onSubmit={submit}><label>{t('Reason')}<textarea name="reason" required maxLength={1000} rows={4} /></label><button className="button primary" disabled={store.busy}><Flag size={16} />{t('Send report')}</button></form></Dialog>;
}
