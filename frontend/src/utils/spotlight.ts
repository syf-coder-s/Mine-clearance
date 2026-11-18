import type { MouseEvent } from 'react';

/** 鼠标跟随光效：把光标位置写进卡片 CSS 变量，供 .card-spotlight 渲染光斑 */
export function trackSpotlight(e: MouseEvent<HTMLElement>) {
  const el = e.currentTarget;
  const r = el.getBoundingClientRect();
  el.style.setProperty('--mx', `${e.clientX - r.left}px`);
  el.style.setProperty('--my', `${e.clientY - r.top}px`);
}
