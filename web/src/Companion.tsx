import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight, Check, Flag, Heart, HeartHandshake, Leaf, LockKeyhole, MessageCircle, Pause, Send, ShieldCheck, Sprout, Sun, Users } from 'lucide-react';
import { Avatar, Dialog, Empty, GardenArt } from './components';
import { ReportDialog } from './ReportDialog';
import { useI18n } from './i18n';
import { usePage } from './usePage';
import type { Dearly } from './useDearly';
import { activeConnection, fromSwift, gardenStage, mergeByID, supportLabels, utcDay, type Connection, type Message, type Profile } from './types';

export function CompanionPage({ store }: { store: Dearly }) {
  const { t } = useI18n();
  const state = store.envelope!.state;
  const me = state.profiles.find(p => p.id === state.currentUserID)!;
  const connection = activeConnection(state);
  const profile = (id: string) => state.profiles.find(p => p.id === id);
  const suggestions = (state.suggestedUserIDs ?? []).map(profile).filter((p): p is Profile => Boolean(p));
  return <><div data-guide="companion" className="page-heading"><span className="eyebrow">{t('SOMEONE TO LISTEN')}</span><h1>{t(connection ? 'A conversation, at your pace.' : 'Good things begin with hello.')}</h1><p>{t('No perfect words needed. Just a little curiosity and a little kindness.')}</p></div>
    {connection ? <ChatView key={connection.id} store={store} connection={connection} /> : <>
      {!me.ageVerified && <div className="notice"><ShieldCheck size={23} /><div><strong>{t('One small step before connecting.')}</strong><p>{t('Age verification is required for companion matching. Ask your Dearly administrator to review your date of birth.')}</p></div></div>}
      {state.invitations.length > 0 && <section className="card invitations"><h2>{t('A hello is waiting')}</h2>{state.invitations.map(invitation => {
        const incoming = invitation.recipientID === me.id;
        const other = profile(incoming ? invitation.senderID : invitation.recipientID);
        return <div className="invitation-row" key={invitation.id}><Avatar name={other?.nickname ?? '?'} /><div><strong>{other?.nickname ?? t('A friend')}</strong><small>{t(incoming ? 'Would like to connect with you' : 'Your invitation is waiting for a reply')}</small></div><div className="row-actions">{incoming && <button className="button primary small" disabled={store.busy} onClick={() => void store.act('invitation.accept', { id: invitation.id })}><Check size={15} />{t('Accept')}</button>}<button className="button secondary small" disabled={store.busy} onClick={() => void store.act('invitation.dismiss', { id: invitation.id })}>{t(incoming ? 'Decline' : 'Withdraw')}</button></div></div>;
      })}<p className="field-help">{t('Chat opens only when both people agree. You can leave a connection at any time.')}</p></section>}
      <div className="section-heading"><div><h2>{t('People you might connect with')}</h2><p>{t('Compatible ages. A shared interest. A place to start.')}</p></div></div>
      {suggestions.length ? <div className="people-grid">{suggestions.map(person => {
        const pending = state.invitations.some(i => [i.senderID, i.recipientID].includes(person.id));
        return <article className="card person-card" key={person.id}><Avatar large name={person.nickname} /><h2>{person.nickname}</h2><span className="muted">{person.age} · {t('Verified')}</span><p>{person.bio || t('A little space for a new connection.')}</p><div className="filter-chips">{person.interests.map(interest => <span className="badge" key={interest}>{interest}</span>)}</div><div className="support-line"><HeartHandshake size={16} />{t(supportLabels[person.support])}</div><p className="field-help">{person.pace}</p><button className="button primary full" disabled={store.busy || pending} onClick={() => void store.act('invitation.send', { userID: person.id })}>{t(pending ? 'Invitation pending' : 'Send a little hello')}{!pending && <ArrowRight size={16} />}</button></article>;
      })}</div> : <Empty icon={<Users size={27} />} title={me.ageVerified ? 'Your next hello is on its way.' : 'A thoughtful connection is worth waiting for.'}>{t(me.ageVerified ? 'No compatible companions are available right now. Check back as more people join.' : 'You can keep journaling and explore the community while your age is reviewed.')}</Empty>}
    </>}
  </>;
}

function ChatView({ store, connection }: { store: Dearly; connection: Connection }) {
  const { t, language } = useI18n();
  const state = store.envelope!.state;
  const other = state.profiles.find(p => p.id === connection.members.find(id => id !== state.currentUserID));
  const history = usePage<Message>(`messages?connectionID=${encodeURIComponent(connection.id)}&limit=50`, store.setError);
  const messages = mergeByID(history.items, state.messages.filter(m => m.connectionID === connection.id)).sort((a, b) => a.date - b.date || a.id.localeCompare(b.id));
  const [text, setText] = useState('');
  const [report, setReport] = useState(false);
  const [ending, setEnding] = useState<'leave' | 'block' | null>(null);
  const scrolling = useRef<HTMLDivElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const latest = messages.at(-1)?.id;
  useEffect(() => { if (nearBottom.current) bottom.current?.scrollIntoView({ block: 'nearest' }); }, [latest]);
  const send = async (event: FormEvent) => {
    event.preventDefault(); if (!text.trim()) return;
    if (await store.act('message.send', { connectionID: connection.id, text })) { setText(''); nearBottom.current = true; bottom.current?.scrollIntoView({ block: 'nearest' }); }
  };
  const shared = state.journals.filter(j => j.audience === 'companion' && j.connectionID === connection.id);
  return <div className="chat-layout"><section className="card chat-card"><header className="chat-header"><Avatar name={other?.nickname ?? '?'} /><div><h2>{other?.nickname ?? t('Your companion')}</h2><span className="connection-status"><span className="status-dot" />{t(store.chatStatus === 'connected' ? 'Live chat connected' : 'Reconnecting · messages can still be sent')}</span></div><LockKeyhole size={17} className="muted" /></header>
    <div className="chat-messages" ref={scrolling} onScroll={() => { const el = scrolling.current!; nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }} aria-live="polite" aria-relevant="additions" role="log" aria-label={t('Conversation')}>
      {history.cursor && <button className="button secondary small history-button" disabled={history.loading} onClick={history.more}>{t(history.loading ? 'Loading…' : 'Earlier messages')}</button>}
      {!messages.length && <Empty icon={<MessageCircle size={24} />} title="A simple hello is enough.">{t('Take your time. This is a space to listen and be heard.')}</Empty>}
      {messages.map(message => <div className={`message ${message.senderID === state.currentUserID ? 'mine' : ''}`} key={message.id}><p>{message.text}</p><time dateTime={fromSwift(message.date).toISOString()}>{fromSwift(message.date).toLocaleTimeString(language === 'vi' ? 'vi-VN' : 'en-US', { hour: '2-digit', minute: '2-digit' })}</time></div>)}<div ref={bottom} />
    </div><form className="message-form" onSubmit={send}><label className="sr-only" htmlFor="chat-message">{t('Your message')}</label><textarea id="chat-message" rows={2} value={text} onChange={e => setText(e.target.value)} maxLength={4000} required placeholder={t('A thought, a hello, a little kindness…')} /><button className="button primary" disabled={store.busy || !text.trim()} aria-label={t('Send message')}><Send size={19} /></button></form><p className="chat-hint">{t('Only the two members of this connection can access this chat.')}</p>
    </section><aside className="stack"><section className="card companion-summary"><span className="small-icon"><Leaf size={22} /></span><h2>{t('A connection with room to breathe.')}</h2><p>{t('Reply when you can. Ask before giving advice. It is okay to take a break.')}</p><hr /><button className="text-button" onClick={() => setReport(true)}><Flag size={15} />{t('Report account')}</button><button className="text-button" onClick={() => setEnding('leave')}>{t('Leave connection')}</button><button className="text-button danger-text" onClick={() => setEnding('block')}>{t('Block account')}</button></section>
      {shared.length > 0 && <section className="card"><h2>{t('Shared between you')}</h2>{shared.map(entry => <div className="shared-entry" key={entry.id}><small>{state.profiles.find(p => p.id === entry.authorID)?.nickname}</small><p>{entry.sharedText}</p></div>)}</section>}
    </aside>{report && other && <ReportDialog store={store} payload={{ userID: other.id }} close={() => setReport(false)} />}
    {ending && <Dialog title={ending === 'block' ? 'Block this account?' : 'Leave this connection?'} close={() => setEnding(null)}><p>{t('This ends the chat. Your garden rewards will remain in your saved gardens.')}</p><div className="dialog-actions"><button className="button secondary" onClick={() => setEnding(null)}>{t('Stay')}</button><button className="button danger" disabled={store.busy} onClick={() => void store.act(ending === 'block' ? 'user.block' : 'connection.leave', ending === 'block' ? { userID: other?.id } : { connectionID: connection.id })}>{t(ending === 'block' ? 'Block account' : 'Leave connection')}</button></div></Dialog>}
  </div>;
}

export function GardenPage({ store, find }: { store: Dearly; find: () => void }) {
  const { t, date } = useI18n();
  const { state, serverNow } = store.envelope!;
  const connection = activeConnection(state);
  const archives = usePage<Connection>('connections?limit=20', store.setError);
  const profiles = mergeByID(archives.profiles, state.profiles);
  const otherName = (c: Connection) => profiles.find(p => p.id === c.members.find(id => id !== state.currentUserID))?.nickname ?? t('A friend');
  const checked = connection?.checkIns[utcDay(serverNow)] ?? [];
  return <><div className="page-heading"><span className="eyebrow">{t('SMALL ACTS, GROWING TOGETHER')}</span><h1>{t('A little care goes a long way.')}</h1><p>{t('Two people showing up. One little garden, growing at its own pace.')}</p></div>
    {connection ? <section className="garden-feature card"><div className="garden-visual"><GardenArt stage={gardenStage(connection)} /><span className="garden-label"><Leaf size={14} />{t(connection.paused ? 'Taking a little rest' : 'Growing, one day at a time')}</span></div><div className="garden-info"><span className="eyebrow">{t('YOUR SHARED GARDEN')}</span><h2>{t('You')} & {otherName(connection)}</h2><p>{t('When you both check in on the same UTC day, your garden grows a little more.')}</p><div className="garden-stats"><div><strong>{connection.serverTotalDays}</strong><span>{t('days together')}</span></div><div><strong>{connection.serverCurrentStreak}</strong><span>{t('day streak')}</span></div><div><strong>{connection.bestStreak}</strong><span>{t('best streak')}</span></div></div>
      <div className="checkin-list">{connection.members.map(id => <div key={id}><Avatar name={profiles.find(p => p.id === id)?.nickname ?? '?'} /><span>{id === state.currentUserID ? t('You') : otherName(connection)}</span><span className={checked.includes(id) ? 'checked' : 'muted'}>{checked.includes(id) ? <><Check size={15} />{t('Here today')}</> : t('A moment to check in')}</span></div>)}</div>
      <button data-guide="garden" className="button primary full" disabled={store.busy || connection.paused || checked.includes(state.currentUserID)} onClick={() => void store.act('connection.checkin', { connectionID: connection.id })}>{checked.includes(state.currentUserID) ? <Check size={18} /> : <Sun size={18} />}{t(checked.includes(state.currentUserID) ? 'You showed up today' : 'I’m here today')}</button><button className="text-button centered" disabled={store.busy} onClick={() => void store.act('connection.pause', { connectionID: connection.id, paused: !connection.paused })}><Pause size={14} />{t(connection.paused ? 'Let the garden grow again' : 'Let the garden rest')}</button>
    </div></section> : <div className="garden-empty card"><GardenArt stage={0} /><Empty icon={<Sprout size={25} />} title="Something lovely can grow here." action={<button data-guide="garden" className="button primary" onClick={find}>{t('Find a companion')}<ArrowRight size={16} /></button>}>{t('A shared garden begins with a connection. Find someone willing to listen, then grow together.')}</Empty></div>}
    <div className="section-heading"><div><h2>{t('Gardens you have grown')}</h2><p>{t('Every connection leaves a little something behind.')}</p></div><Heart size={19} /></div>
    {archives.items.length ? <div className="archive-grid">{archives.items.map(garden => <article className="card archived-garden" key={garden.id}><GardenArt stage={gardenStage(garden)} /><div><h3>{t('You')} & {otherName(garden)}</h3><p>{date(garden.startedAt)} — {garden.endedAt !== null ? date(garden.endedAt) : ''}</p><div className="filter-chips"><span className="badge">{garden.serverTotalDays} {t('days together')}</span><span className="badge">{garden.bestStreak} {t('best streak')}</span></div></div></article>)}</div> : <p className="quiet-note">{t('Your saved gardens will be kept here, even after a connection ends.')}</p>}
    {archives.cursor && <div className="load-more"><button className="button secondary" disabled={archives.loading} onClick={archives.more}>{t('More saved gardens')}</button></div>}
  </>;
}
