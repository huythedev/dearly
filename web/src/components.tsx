import { useEffect, useId, useRef, type ReactNode } from 'react';
import { Leaf, X } from 'lucide-react';
import { useI18n } from './i18n';

export function Brand() { return <span className="brand"><span className="brand-mark"><Leaf size={23} /></span>dearly<span className="brand-dot">.</span></span>; }
export function Avatar({ name, large = false }: { name: string; large?: boolean }) {
  return <span aria-hidden="true" className={`avatar ${large ? 'large' : ''}`}>{name.slice(0, 1).toUpperCase() || <Leaf size={19} />}</span>;
}
export function Empty({ icon, title, children, action }: { icon: ReactNode; title: string; children: ReactNode; action?: ReactNode }) {
  const { t } = useI18n();
  return <div className="empty"><span className="empty-icon">{icon}</span><h2>{t(title)}</h2><p>{children}</p>{action}</div>;
}
export function Dialog({ title, children, close }: { title: string; children: ReactNode; close: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  const { t } = useI18n();
  useEffect(() => { const dialog = ref.current!; dialog.showModal(); return () => dialog.close(); }, []);
  return <dialog ref={ref} className="dialog" aria-labelledby={id} onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === ref.current) close(); }}>
    <div className="dialog-heading"><h2 id={id}>{t(title)}</h2><button type="button" className="icon-button" onClick={close} aria-label={t('Close')}><X size={20} /></button></div>{children}
  </dialog>;
}
export function GardenArt({ stage = 2 }: { stage?: number }) {
  const id = useId().replace(/:/g, '');
  return <svg className="garden-art" viewBox="0 0 600 360" role="img" aria-label={useI18n().t('A little garden growing together')}>
    <defs><linearGradient id={id} x2="0" y2="1"><stop stopColor="var(--garden-sky)" /><stop offset="1" stopColor="var(--garden-horizon)" /></linearGradient></defs>
    <rect width="600" height="360" rx="28" fill={`url(#${id})`} />
    <circle className="garden-sun" cx="465" cy="85" r="33" fill="var(--garden-sun)" />
    <path d="M0 242Q130 161 310 236T600 212V360H0Z" fill="var(--garden-back)" />
    <path d="M0 272Q180 221 350 269T600 252V360H0Z" fill="var(--garden-front)" />
    <ellipse cx="301" cy="301" rx="112" ry="17" fill="var(--garden-shadow)" />
    <path d="M245 284h114l-13 48h-89Z" fill="#be987b" /><path d="M240 281h124v13H240Z" fill="#d8b79c" />
    <path d="M302 281v-61" stroke="#406951" strokeWidth="7" strokeLinecap="round" />
    <path d="M300 258q-59 5-50-45 50-1 50 45M304 244q-4-46 48-49 5 46-48 49" fill="#688d63" />
    {stage >= 1 && <path d="M302 230q-30-39 4-64 31 30-4 64" fill="#88a279" />}
    {stage >= 2 && <g fill="#e7b99e"><circle cx="305" cy="161" r="14" /><circle cx="284" cy="176" r="14" /><circle cx="325" cy="176" r="14" /><circle cx="292" cy="195" r="14" /><circle cx="316" cy="195" r="14" /><circle cx="305" cy="180" r="10" fill="#f6e7af" /></g>}
    {stage >= 3 && <g><path d="M201 290v-53M402 288v-56" stroke="#527551" strokeWidth="5" /><path d="M201 271q-30-2-29-23 26-2 29 23M402 265q24 0 27-23-26 0-27 23" fill="#88a279" /><circle cx="202" cy="229" r="13" fill="#e9dcae" /><circle cx="403" cy="223" r="13" fill="#e7b99e" /></g>}
    {stage >= 4 && <g fill="#8ea77e"><path d="M111 306q-32-49 6-62 26 34-6 62M479 306q-28-44 6-58 28 34-6 58" /></g>}
    {stage >= 5 && <g fill="#edd4ad"><circle cx="116" cy="245" r="13" /><circle cx="483" cy="247" r="14" /></g>}
    <g fill="#efdfb6"><circle cx="163" cy="123" r="3" /><circle cx="376" cy="109" r="3" /><circle cx="421" cy="154" r="2" /></g>
  </svg>;
}
