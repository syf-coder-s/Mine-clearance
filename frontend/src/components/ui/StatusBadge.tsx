type BadgeTone = 'primary' | 'success' | 'warning' | 'danger' | 'neutral';

const TONE_CLASS: Record<BadgeTone, string> = {
  primary: 'badge badge-primary',
  success: 'badge badge-success',
  warning: 'badge badge-warning',
  danger: 'badge badge-danger',
  neutral: 'badge badge-neutral',
};

interface StatusBadgeProps {
  tone: BadgeTone;
  children: React.ReactNode;
  dot?: boolean;
}

/** 状态标签（低饱和状态色） */
export function StatusBadge({ tone, children, dot = true }: StatusBadgeProps) {
  return (
    <span className={TONE_CLASS[tone]}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />}
      {children}
    </span>
  );
}

/** 会话/训练状态 → 标签 */
export function SessionStatusBadge({ status }: { status: string }) {
  if (status === 'finished') return <StatusBadge tone="success">已完成</StatusBadge>;
  if (status === 'in_progress') return <StatusBadge tone="primary">进行中</StatusBadge>;
  return <StatusBadge tone="neutral">{status}</StatusBadge>;
}