interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

/** 加载失败状态 */
export function ErrorState({ title = '加载失败', message, onRetry }: ErrorStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 6,
        padding: '48px 24px',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: 12,
          background: 'var(--danger-soft)',
          border: '1px solid var(--danger-line)',
          color: 'var(--danger)',
          display: 'grid',
          placeItems: 'center',
          marginBottom: 6,
        }}
        aria-hidden
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <path d="M12 8v5M12 16.5h.01" />
          <circle cx="12" cy="12" r="9" />
        </svg>
      </div>
      <div style={{ fontSize: 13.5, fontWeight: 600 }}>{title}</div>
      {message && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 420, lineHeight: 1.7 }}>{message}</div>
      )}
      {onRetry && (
        <button className="btn btn-outline btn-sm" style={{ marginTop: 12 }} onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  );
}
