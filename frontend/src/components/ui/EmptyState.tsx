import type { ReactNode } from 'react';

interface EmptyStateProps {
  title: string;
  desc?: string;
  action?: ReactNode;
}

/** 空数据状态 */
export function EmptyState({ title, desc, action }: EmptyStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 6,
        padding: '56px 24px',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          width: 44,
          height: 44,
          borderRadius: 12,
          background: 'var(--bg-elev)',
          border: '1px dashed var(--border-strong)',
          display: 'grid',
          placeItems: 'center',
          color: 'var(--text-tertiary)',
          marginBottom: 6,
        }}
        aria-hidden
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
          <path d="M4 7h16M4 12h10M4 17h7" />
        </svg>
      </div>
      <div style={{ fontSize: 13.5, fontWeight: 600 }}>{title}</div>
      {desc && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 380, lineHeight: 1.7 }}>{desc}</div>
      )}
      {action && <div style={{ marginTop: 12 }}>{action}</div>}
    </div>
  );
}
