import { useState, type FormEvent } from 'react';
import { Check, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { Dialog, Empty } from './components';
import { useI18n } from './i18n';
import { usePage } from './usePage';
import type { Dearly } from './useDearly';
import type { AuditEntry, StaffReport, StaffUser } from './types';

export function StaffPage({ store }: { store: Dearly }) {
  const { t } = useI18n();
  const [section, setSection] = useState('reports');
  const permissions = store.envelope!.state.permissions ?? [];
  return <><div className="page-heading"><span className="eyebrow">{t('CARE FOR THE COMMUNITY')}</span><h1>{t('Dearly management')}</h1><p>{t('Review reports and care for the space we share.')}</p></div>
    <div className="filter-chips staff-tabs"><button className={`chip ${section === 'reports' ? 'selected' : ''}`} onClick={() => setSection('reports')}>{t('Reports')}</button>{permissions.includes('users.read') && <button className={`chip ${section === 'users' ? 'selected' : ''}`} onClick={() => setSection('users')}>{t('Accounts')}</button>}{permissions.includes('audit.read') && <button className={`chip ${section === 'audit' ? 'selected' : ''}`} onClick={() => setSection('audit')}>{t('Audit log')}</button>}</div>
    {section === 'reports' && <Reports store={store} />}
    {section === 'users' && permissions.includes('users.read') && <Accounts store={store} />}
    {section === 'audit' && permissions.includes('audit.read') && <Audit store={store} />}
  </>;
}

function Reports({ store }: { store: Dearly }) {
  const { t, date } = useI18n();
  const [status, setStatus] = useState('open');
  const [review, setReview] = useState<{ report: StaffReport; action: 'review' | 'hide' | 'restore' } | null>(null);
  const page = usePage<StaffReport>(`staff/reports?status=${status}`, store.setError);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const fields = Object.fromEntries(new FormData(event.currentTarget));
    if (review && await store.act(`staff.report.${review.action}`, { id: review.report.id, ...fields })) { setReview(null); await page.reload(); }
  };
  return <><div className="section-heading"><label>{t('Report status')}<select value={status} onChange={e => setStatus(e.target.value)}>{['open', 'reviewed', 'dismissed'].map(value => <option key={value} value={value}>{t(value)}</option>)}</select></label><button className="button secondary small" onClick={() => void page.reload()} disabled={page.loading}><RefreshCw size={14} />{t('Refresh')}</button></div>
    <div className="stack">{page.items.map(report => <article className="card" key={report.id}><header className="report-heading"><h2>{report.reportedNickname}</h2><span className="badge">{t(report.status)}</span></header><small className="muted">{t('Reported by')} {report.reporterNickname} · {date(report.date)}</small><p className="preserve-text">{report.reason}</p>{report.evidence && <blockquote className="report-evidence"><small>{t('Reported public passage')}</small><p>{report.evidence}</p></blockquote>}{report.reviewNote && <p className="field-help">{t('Review note')}: {report.reviewNote}</p>}<div className="row-actions wrap"><button className="button secondary small" onClick={() => setReview({ report, action: 'review' })}>{t('Review report')}</button>{report.canHide && <button className="button secondary small" onClick={() => setReview({ report, action: 'hide' })}>{t('Hide community post')}</button>}{report.canRestore && <button className="button secondary small" onClick={() => setReview({ report, action: 'restore' })}>{t('Remove sharing restriction')}</button>}</div></article>)}</div>
    {!page.loading && !page.items.length && <Empty icon={<ShieldCheck size={25} />} title="All quiet here.">{t('There are no reports with this status.')}</Empty>}
    {page.cursor && <div className="load-more"><button className="button secondary" onClick={page.more} disabled={page.loading}>{t('More reports')}</button></div>}
    {review && <Dialog title={review.action === 'review' ? 'Review report' : review.action === 'hide' ? 'Hide community post' : 'Remove sharing restriction'} close={() => setReview(null)}><form onSubmit={submit}>{review.action === 'review' && <label>{t('Status')}<select name="status" defaultValue={review.report.status}>{['open', 'reviewed', 'dismissed'].map(value => <option key={value} value={value}>{t(value)}</option>)}</select></label>}<label>{t('Reason for the audit log')}<textarea name="reason" required maxLength={1000} rows={3} /></label><button className="button primary" disabled={store.busy}><Check size={16} />{t('Save decision')}</button></form></Dialog>}
  </>;
}

function Accounts({ store }: { store: Dearly }) {
  const { t } = useI18n();
  const [query, setQuery] = useState('');
  const [input, setInput] = useState('');
  const [editing, setEditing] = useState<{ user: StaffUser; action: 'role' | 'suspend' | 'verify_age' } | null>(null);
  const page = usePage<StaffUser>(`staff/users?q=${encodeURIComponent(query)}`, store.setError);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (!editing) return;
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    const payload = { userID: editing.user.id, ...fields, ...(editing.action === 'suspend' ? { suspended: !editing.user.suspended } : {}) };
    if (await store.act(`staff.user.${editing.action}`, payload)) { setEditing(null); await page.reload(); }
  };
  return <><form className="search-box account-search" onSubmit={event => { event.preventDefault(); setQuery(input); }}><Search size={18} /><input value={input} onChange={e => setInput(e.target.value)} maxLength={64} placeholder={t('Search username or nickname prefix…')} aria-label={t('Search accounts')} /><button className="button primary small">{t('Search')}</button></form>
    <p className="field-help">{t('Admin accounts are managed with the server CLI. Web administration can manage members and moderators.')}</p>
    <div className="stack">{page.items.map(user => {
      const editable = user.role !== 'admin' && user.id !== store.envelope!.state.currentUserID;
      return <article className="card account-card" key={user.id}><div><h2>{user.nickname}</h2><span className="muted">@{user.username} · {t(user.role)}</span><p>{t('Date of birth')}: {user.birthDate} · {t(user.ageVerified ? 'Verified' : 'Unverified')} · {t(user.suspended ? 'Suspended' : 'Active')}</p></div>{editable && <div className="row-actions wrap"><button className="button secondary small" onClick={() => setEditing({ user, action: 'verify_age' })}>{t('Verify age')}</button><button className="button secondary small" onClick={() => setEditing({ user, action: 'role' })}>{t('Change role')}</button><button className="button secondary small" onClick={() => setEditing({ user, action: 'suspend' })}>{t(user.suspended ? 'Restore account' : 'Suspend account')}</button></div>}</article>;
    })}</div>
    {!page.items.length && !page.loading && <p>{t('No accounts found.')}</p>}
    {page.cursor && <div className="load-more"><button className="button secondary" onClick={page.more} disabled={page.loading}>{t('More accounts')}</button></div>}
    {editing && <Dialog title={editing.action === 'role' ? 'Change role' : editing.action === 'verify_age' ? 'Verify age' : editing.user.suspended ? 'Restore account' : 'Suspend account'} close={() => setEditing(null)}><p>{editing.user.nickname} · @{editing.user.username}</p><form onSubmit={submit}>
      {editing.action === 'role' && <label>{t('Role')}<select name="role" defaultValue={editing.user.role}><option value="user">{t('user')}</option><option value="moderator">{t('moderator')}</option></select></label>}
      {editing.action === 'verify_age' && <><label>{t('Reviewed date of birth')}<input name="birthDate" type="date" defaultValue={editing.user.birthDate} required /></label><p className="field-help">{t('Correcting the date ends existing connections so eligibility can be reviewed again.')}</p></>}
      <label>{t('Reason for the audit log')}<textarea name="reason" required rows={3} maxLength={1000} /></label><button className="button primary" disabled={store.busy}>{t('Save decision')}</button>
    </form></Dialog>}
  </>;
}

function Audit({ store }: { store: Dearly }) {
  const { t, date } = useI18n();
  const page = usePage<AuditEntry, number>('staff/audit', store.setError);
  return <><div className="section-heading"><h2>{t('Administration audit log')}</h2><button className="button secondary small" onClick={() => void page.reload()} disabled={page.loading}><RefreshCw size={14} />{t('Refresh')}</button></div><div className="stack">{page.items.map(entry => <article className="card audit-entry" key={entry.id}><div><span className="badge">{entry.action}</span><small>{date(entry.date)} · {entry.actorName}</small></div><p>{entry.detail.reason || entry.detail.note || t('No note')}</p><code>{entry.targetID}</code></article>)}</div>{page.cursor !== null && <div className="load-more"><button className="button secondary" onClick={page.more} disabled={page.loading}>{t('More audit events')}</button></div>}</>;
}
