import { useState } from 'react';
import type { EvidenceItem } from '../../types/training';
import { IconChevronRight } from '../../components/icons';

interface EvidencePanelProps {
  evidence: EvidenceItem[];
  citedIds: string[];
  onToggleCite: (evidenceId: string) => void;
  /** 点击「定位」按钮：跳转代码面板并高亮对应行 */
  onLocate?: (ev: EvidenceItem) => void;
}

/** 可折叠证据面板：只展示后端授权字段 */
export function EvidencePanel({ evidence, citedIds, onToggleCite, onLocate }: EvidencePanelProps) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        style={{
          width: '100%',
          padding: '12px 16px',
          background: 'transparent',
          border: 'none',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          cursor: 'pointer',
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--text-main)',
        }}
        aria-expanded={open}
      >
        <span
          style={{
            display: 'grid',
            placeItems: 'center',
            transition: 'transform .18s',
            transform: open ? 'rotate(90deg)' : 'none',
            color: 'var(--text-tertiary)',
          }}
        >
          <IconChevronRight size={13} />
        </span>
        证据与引用
        <span className="badge">{evidence.length}</span>
        {citedIds.length > 0 && <span className="badge badge-primary">已引用 {citedIds.length}</span>}
        <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 400, color: 'var(--text-tertiary)' }}>
          仅展示后端授权内容
        </span>
      </button>

      {open && (
        <div style={{ padding: '0 16px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {evidence.length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>本题暂无可用证据。</div>
          )}
          {evidence.map((ev) => {
            const cited = citedIds.includes(ev.evidence_id);
            return (
              <div key={ev.evidence_id} className={`evidence-row${cited ? ' is-cited' : ''}`}>
                <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', flex: 1, minWidth: 0, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={cited}
                    onChange={() => onToggleCite(ev.evidence_id)}
                    style={{ marginTop: 3, accentColor: 'var(--primary)' }}
                  />
                  <div style={{ minWidth: 0 }}>
                    <div className="evidence-id">{ev.evidence_id}</div>
                    {ev.visible_in_code ? (
                      <div style={{ marginTop: 4, color: 'var(--text-main)', lineHeight: 1.65 }}>{ev.excerpt}</div>
                    ) : (
                      <div style={{ marginTop: 4, color: 'var(--text-tertiary)' }}>（该证据暂无可展示内容）</div>
                    )}
                  </div>
                </label>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ flexShrink: 0, alignSelf: 'center' }}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (onLocate) onLocate(ev);
                  }}
                >
                  定位
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
