import type { ReactNode } from 'react';

/**
 * 训练工作台全屏布局：不套用公共侧栏，把空间留给代码阅读与对抗交互。
 * 顶部状态栏 + 三栏主体由页面自行组织。
 */
export function TrainingLayout({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--bg)',
        overflow: 'hidden',
      }}
    >
      {children}
    </div>
  );
}