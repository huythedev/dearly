export interface Box { x: number; y: number; width: number; height: number }
export interface Viewport { width: number; height: number }
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(value, Math.max(low, high)));

export function spotlight(box: Box, viewport: Viewport): Box | null {
  const left = Math.max(4, box.x - 7), top = Math.max(4, box.y - 7);
  const right = Math.min(viewport.width - 4, box.x + box.width + 7);
  const bottom = Math.min(viewport.height - 4, box.y + box.height + 7);
  return right > left && bottom > top ? { x: left, y: top, width: right - left, height: bottom - top } : null;
}

export function guidePlacement(target: Box | null, viewport: Viewport, measuredHeight: number) {
  const margin = 16, gap = 16;
  const width = Math.min(380, Math.max(0, viewport.width - margin * 2));
  const available = Math.max(0, viewport.height - margin * 2);
  const above = target ? Math.max(0, target.y - gap - margin) : available;
  const below = target ? Math.max(0, viewport.height - margin - target.y - target.height - gap) : available;
  // On a short viewport the copy scrolls, keeping navigation buttons reachable.
  const maxHeight = target ? Math.min(available, Math.max(200, above, below)) : available;
  const height = Math.min(measuredHeight, maxHeight);
  let top = (viewport.height - height) / 2;
  if (target) {
    top = below >= height ? target.y + target.height + gap
      : above >= height ? target.y - gap - height
      : below >= above ? viewport.height - margin - height : margin;
  }
  return {
    width, maxHeight,
    left: clamp(target ? target.x + target.width / 2 - width / 2 : (viewport.width - width) / 2, margin, viewport.width - margin - width),
    top: clamp(top, margin, viewport.height - margin - height),
  };
}
