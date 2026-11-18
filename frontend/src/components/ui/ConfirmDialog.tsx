import type { ReactNode } from 'react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  desc?: ReactNode;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 确认对话框（模态） */
export function ConfirmDialog({
  open,
  title,
  desc,
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(16, 22, 35, 0.32)',
        backdropFilter: 'blur(3px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 24,
      }}
      onClick={onCancel}
    >
      <div
        className="card"
        style={{
          width: 440,
          maxWidth: '100%',
          boxShadow: 'var(--shadow-pop)',
          overflow: 'hidden',
          animation: 'mc-fade-up .18s ease both',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ padding: '20px 22px 0' }}>
          <h3 style={{ fontSize: 15.5, letterSpacing: '-0.01em' }}>{title}</h3>
          {desc && (
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginTop: 8, lineHeight: 1.7 }}>
              {desc}
            </div>
          )}
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            padding: '18px 22px',
            marginTop: 4,
            background: 'var(--bg-hover)',
            borderTop: '1px solid var(--border-hair)',
          }}
        >
          <button className="btn btn-outline" onClick={onCancel} disabled={loading}>
            {cancelText}
          </button>
          <button
            className={danger ? 'btn btn-danger-outline' : 'btn btn-primary'}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? '处理中…' : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
