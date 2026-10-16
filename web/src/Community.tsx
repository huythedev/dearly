import { useState, type FormEvent } from 'react';
import { ArrowRight, Feather, Flag, Heart, MessageCircle, MoreHorizontal, Send, ShieldCheck, Users } from 'lucide-react';
import { Avatar, Dialog, Empty } from './components';
import { useI18n } from './i18n';
import { ReportDialog } from './ReportDialog';
import type { Dearly } from './useDearly';
import { supportLabels, type Journal } from './types';

export function CommunityPage({ store, write }: { store: Dearly; write: () => void }) {
  const { t } = useI18n();
  const state = store.envelope!.state;
  const [filter, setFilter] = useState('all');
  const posts = state.journals.filter(j => j.audience === 'community' && (filter === 'all' || j.support === filter)).sort((a, b) => b.date - a.date || b.id.localeCompare(a.id));
  return <><div className="page-heading heading-with-action"><div><span className="eyebrow">{t('A LITTLE LESS ALONE')}</span><h1>{t('There is room for you here.')}</h1><p>{t('Real feelings. Shared gently. Sometimes listening is everything.')}</p></div><button className="button primary" onClick={write}><Feather size={17} />{t('Share a thought')}</button></div>
    <div className="community-layout"><div><div className="filter-chips"><button data-guide="community" className={filter === 'all' ? 'chip selected' : 'chip'} onClick={() => setFilter('all')}>{t('All stories')}</button>{Object.entries(supportLabels).map(([key, title]) => <button key={key} className={filter === key ? 'chip selected' : 'chip'} onClick={() => setFilter(key)}>{t(title)}</button>)}</div>
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

