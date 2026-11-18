interface LoadingStateProps {
  text?: string;
  full?: boolean;
}

/** 加载中状态 */
export function LoadingState({ text = '加载中…', full = false }: LoadingStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        padding: full ? '140px 24px' : '48px 24px',
        color: 'var(--text-tertiary)',
        fontSize: 12.5,
      }}
    >
      <span
        style={{
          width: 20,
          height: 20,
          border: '2px solid var(--border)',
          borderTopColor: 'var(--primary)',
          borderRadius: '50%',
          animation: 'mc-spin 0.8s linear infinite',
        }}
        aria-hidden
      />
      {text}
    </div>
  );
}
