import { createContext, useContext, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowLeft, ArrowRight, Check, Leaf } from 'lucide-react';
import { useI18n } from '../i18n';
import { guidePlacement, spotlight, type Box, type Viewport } from './layout';
import { guideSteps, hasSeenGuide, rememberGuide, type GuideRoute } from './model';
import './guide.css';

const Context = createContext({ start: () => {} });
export const useGuide = () => useContext(Context);

export function GuidedTour({ userID, navigate, currentRoute, children }: {
  userID: string; navigate: (route: GuideRoute) => void; currentRoute: string; children: ReactNode;
}) {
  const [index, setIndex] = useState<number | null>(() => hasSeenGuide(userID) ? null : -1);
  const dismiss = () => { rememberGuide(userID); setIndex(null); };
  const go = (next: number) => {
    if (next >= guideSteps.length) { dismiss(); return; }
    navigate(guideSteps[next].route);
    setIndex(next);
  };
  const dismissRef = useRef(dismiss); dismissRef.current = dismiss;
  useEffect(() => {
    // Browser Back/Forward can leave the current guide screen even with a modal open.
    if (index !== null && index >= 0 && currentRoute !== guideSteps[index].route) dismissRef.current();
  }, [currentRoute, index]);

  return <Context value={{ start: () => go(0) }}>
    {children}
    {index !== null && <GuideDialog index={index} next={() => go(index + 1)} back={() => go(index - 1)} dismiss={dismiss} />}
  </Context>;
}

function GuideDialog({ index, next, back, dismiss }: { index: number; next: () => void; back: () => void; dismiss: () => void }) {
  const { t } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [target, setTarget] = useState<Box | null>(null);
  const [viewport, setViewport] = useState<Viewport>({ width: innerWidth, height: innerHeight });
  const [cardHeight, setCardHeight] = useState(280);
  const maskID = useId();
  const step = index >= 0 ? guideSteps[index] : null;

  useLayoutEffect(() => {
    const element = dialog.current!;
    const overflow = document.documentElement.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : null;
    document.documentElement.style.overflow = 'hidden';
    element.showModal();
    return () => {
      element.close();
      document.documentElement.style.overflow = overflow;
      const restore = previousFocus?.isConnected ? previousFocus : document.querySelector<HTMLElement>('[data-guide="settings"]');
      // Restore after React removes the dialog, including a replay button on a route we just left.
      queueMicrotask(() => restore?.focus({ preventScroll: true }));
    };
  }, []);

  useLayoutEffect(() => {
    let frame = 0;
    let observed: Element | null = null;
    const targetSelector = step ? `[data-guide="${step.target}"]` : '';
    const resize = new ResizeObserver(() => schedule());
    const measure = () => {
      frame = 0;
      const bounds = dialog.current!.getBoundingClientRect();
      const size = { width: bounds.width, height: bounds.height };
      setViewport(previous => previous.width === size.width && previous.height === size.height ? previous : size);
      const element = targetSelector ? document.querySelector(targetSelector) : null;
      if (element !== observed) {
        if (observed) resize.unobserve(observed);
        observed = element;
        if (element) { element.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' }); resize.observe(element); }
      }
      const box = element?.getBoundingClientRect();
      const hole = box ? spotlight({ x: box.x - bounds.x, y: box.y - bounds.y, width: box.width, height: box.height }, size) : null;
      setTarget(previous => JSON.stringify(previous) === JSON.stringify(hole) ? previous : hole);
      const height = card.current!.getBoundingClientRect().height;
      setCardHeight(previous => Math.abs(previous - height) < 1 ? previous : height);
    };
    function schedule() { if (!frame) frame = requestAnimationFrame(measure); }
    const mutations = new MutationObserver(schedule);
    const shell = document.getElementById('app-shell');
    if (shell) mutations.observe(shell, { childList: true, subtree: true });
    resize.observe(card.current!);
    window.addEventListener('resize', schedule);
    window.addEventListener('scroll', schedule, true);
    visualViewport?.addEventListener('resize', schedule);
    heading.current?.focus({ preventScroll: true });
    measure();
    return () => {
      cancelAnimationFrame(frame); resize.disconnect(); mutations.disconnect();
      window.removeEventListener('resize', schedule); window.removeEventListener('scroll', schedule, true);
      visualViewport?.removeEventListener('resize', schedule);
    };
  }, [step]);

  const placement = guidePlacement(target, viewport, cardHeight);
  const progress = t('Step {current} of {total}').replace('{current}', String(index + 1)).replace('{total}', String(guideSteps.length));
  return <dialog ref={dialog} className="guide-dialog" aria-labelledby="guide-title" aria-describedby="guide-description" aria-modal="true"
    onCancel={event => { event.preventDefault(); dismiss(); }}
    onKeyDown={event => {
      if (event.key !== 'Tab') return;
      const controls = Array.from(dialog.current!.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
      const active = controls.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.shiftKey ? (active <= 0 ? controls.length - 1 : active - 1) : (active + 1) % controls.length;
      event.preventDefault(); controls[next]?.focus();
    }}>
    <svg className="guide-shade" width="100%" height="100%" aria-hidden="true">
      <defs><mask id={maskID}><rect width="100%" height="100%" fill="white" />
        {target && <rect {...target} rx="13" fill="black" />}
      </mask></defs>
      <rect width="100%" height="100%" fill="#080908" fillOpacity=".64" mask={`url(#${maskID})`} />
      {target && <rect {...target} rx="13" className="guide-outline" data-guide-hole="true" />}
    </svg>
    <div ref={card} className={`guide-card ${step ? '' : 'guide-intro'}`} style={{ left: placement.left, top: placement.top, width: placement.width, maxHeight: placement.maxHeight }}>
      {step ? <div className="guide-topline"><span>{progress}</span><button type="button" className="text-button" onClick={dismiss}>{t('Skip guide')}</button></div>
        : <span className="small-icon"><Leaf size={23} /></span>}
      <div className="guide-copy">
        <h2 ref={heading} id="guide-title" tabIndex={-1}>{t(step?.title ?? 'A little guide to Dearly')}</h2>
        <p id="guide-description">{t(step?.body ?? 'Explore the main features at your own pace. You can skip the guide and open it again from Settings.')}</p>
      </div>
      {step ? <div className="guide-actions">
        {index > 0 ? <button type="button" className="button secondary small" onClick={back}><ArrowLeft size={16} />{t('Back')}</button> : <span />}
        <button type="button" className="button primary small" onClick={next}>{t(index === guideSteps.length - 1 ? 'Finish' : 'Next')}{index === guideSteps.length - 1 ? <Check size={16} /> : <ArrowRight size={16} />}</button>
      </div> : <div className="guide-intro-actions"><button type="button" className="button primary full" onClick={next}>{t('Show me around')}<ArrowRight size={17} /></button><button type="button" className="text-button" onClick={dismiss}>{t('Maybe later')}</button></div>}
    </div>
  </dialog>;
}
