import type { FormEvent } from 'react';
import { Flag } from 'lucide-react';
import { Dialog } from './components';
import { useI18n } from './i18n';
import type { Dearly } from './useDearly';

export function ReportDialog({ store, payload, close }: { store: Dearly; payload: Record<string, unknown>; close: () => void }) {
  const { t } = useI18n();
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const reason = new FormData(event.currentTarget).get('reason');
    if (await store.act('report.create', { ...payload, reason })) close();
  };
  return <Dialog title="Tell us what happened" close={close}><p>{t('Reports go to Dearly moderators for review.')}</p><form onSubmit={submit}><label>{t('Reason')}<textarea name="reason" required maxLength={1000} rows={4} /></label><button className="button primary" disabled={store.busy}><Flag size={16} />{t('Send report')}</button></form></Dialog>;
}
