import { trackSpotlight } from '../../utils/spotlight';

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  tone?: 'default' | 'primary' | 'success' | 'warning' | 'danger';
  demo?: boolean;
}

const TONE_COLOR: Record<string, string> = {
  default: 'var(--text-main)',
  primary: 'var(--primary)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
};

/** 数据概览卡片：等宽小标 + 大数字 + 说明 */
export function StatCard({ label, value, sub, tone = 'default', demo = false }: StatCardProps) {
  return (
    <div
      className="card card-spotlight"
      onMouseMove={trackSpotlight}
      style={{ position: 'relative', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 6 }}
    >
      {demo && (
        <span className="badge badge-warning" style={{ position: 'absolute', top: 12, right: 12, height: 18, fontSize: 10.5 }}>
          演示
        </span>
      )}
      <div className="micro">{label}</div>
      <div
        className="num"
        style={{
          fontSize: 26,
          fontWeight: 600,
          color: TONE_COLOR[tone],
          lineHeight: 1.1,
          marginTop: 2,
        }}
      >
        {value}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, minHeight: 16 }}>
        {sub && <span style={{ fontSize: 11.5, color: 'var(--text-tertiary)' }}>{sub}</span>}
      </div>
    </div>
  );
}
