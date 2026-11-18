import { useCallback, useEffect, useState } from 'react';

export interface TypewriterOptions {
  /** 每个 tick 前进的字符数，默认 2 */
  step?: number;
  /** tick 间隔毫秒数，默认 24 */
  interval?: number;
  /** 是否启用逐字动画；false 时直接显示全文，默认 true */
  enabled?: boolean;
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * 打字机效果 Hook：整段文本到达后逐字放出（模拟大模型流式输出）。
 * - 文本变化时自动重新播放
 * - 点击场景可用 skip() 立即显示全文
 * - 系统开启「减少动态效果」时自动退化为直接显示
 * - 以后接入后端真流式（SSE）时，只需把不断增长的文本继续传入，展示层复用
 */
export function useTypewriter(text: string, options?: TypewriterOptions) {
  const { step = 2, interval = 24, enabled = true } = options ?? {};
  const [len, setLen] = useState(() =>
    !enabled || !text || prefersReducedMotion() ? text.length : 0,
  );

  useEffect(() => {
    if (!enabled || !text || prefersReducedMotion()) {
      setLen(text.length);
      return;
    }
    setLen(0);
    const timer = window.setInterval(() => {
      setLen((prev) => {
        const next = Math.min(prev + step, text.length);
        if (next >= text.length) window.clearInterval(timer);
        return next;
      });
    }, interval);
    return () => window.clearInterval(timer);
  }, [text, enabled, step, interval]);

  const skip = useCallback(() => setLen(text.length), [text]);

  return { shown: text.slice(0, len), done: len >= text.length, skip };
}
