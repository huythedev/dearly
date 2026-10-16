import { afterEach, describe, expect, it, vi } from 'vitest';
import { guidePlacement, spotlight } from './layout';
import { hasSeenGuide, rememberGuide } from './model';

afterEach(() => vi.unstubAllGlobals());

describe('guide preferences', () => {
  it('remembers dismissal for one account without suppressing another account', () => {
    const saved = new Map<string, string>();
    vi.stubGlobal('localStorage', { getItem: (key: string) => saved.get(key), setItem: (key: string, value: string) => saved.set(key, value) });
    expect(hasSeenGuide('first')).toBe(false);
    rememberGuide('first');
    expect(hasSeenGuide('first')).toBe(true);
    expect(hasSeenGuide('second')).toBe(false);
  });
  it('still opens and dismisses when browser storage is unavailable', () => {
    vi.stubGlobal('localStorage', { getItem() { throw new Error('Unavailable'); }, setItem() { throw new Error('Full'); } });
    expect(hasSeenGuide('first')).toBe(false);
    expect(() => rememberGuide('first')).not.toThrow();
  });
});

describe('spotlight placement', () => {
  it('clips partial targets and excludes targets entirely outside the screen', () => {
    expect(spotlight({ x: -12, y: 20, width: 60, height: 30 }, { width: 320, height: 568 }))
      .toEqual({ x: 4, y: 13, width: 51, height: 44 });
    expect(spotlight({ x: 10, y: 600, width: 60, height: 30 }, { width: 320, height: 568 })).toBeNull();
  });
  it('places instructions above a low control and below a high control', () => {
    const screen = { width: 390, height: 844 };
    const high = guidePlacement({ x: 200, y: 50, width: 100, height: 44 }, screen, 250);
    const low = guidePlacement({ x: 200, y: 700, width: 100, height: 44 }, screen, 250);
    expect(high.top).toBe(110);
    expect(low.top + 250).toBe(684);
  });
  it.each([{ width: 320, height: 568 }, { width: 568, height: 320 }])('keeps navigation inside a short screen: %j', screen => {
    const position = guidePlacement({ x: 200, y: 120, width: 120, height: 90 }, screen, 520);
    expect(position.left).toBeGreaterThanOrEqual(16);
    expect(position.left + position.width).toBeLessThanOrEqual(screen.width - 16);
    expect(position.top).toBeGreaterThanOrEqual(16);
    expect(position.top + Math.min(520, position.maxHeight)).toBeLessThanOrEqual(screen.height - 16);
  });
});
