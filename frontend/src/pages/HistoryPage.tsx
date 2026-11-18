import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DashboardLayout } from '../layouts/DashboardLayout';
import { DataTable, type DataColumn } from '../components/ui/DataTable';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { SessionStatusBadge } from '../components/ui/StatusBadge';
import { listHistory } from '../services/historyService';
import { directionLabel, LANGUAGE_LABELS, type HistoryRecord } from '../mocks/historyMock';

const STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'in_progress', label: '进行中' },
  { value: 'finished', label: '已完成' },
];

/** 训练历史页：表格 + 搜索 + 状态筛选 + 空/加载/失败态 */
export function HistoryPage() {
  const navigate = useNavigate();
  const [records, setRecords] = useState<HistoryRecord[] | null>(null);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const PAGE_SIZE = 8;

  useEffect(() => {
    let alive = true;
    setRecords(null);
    listHistory({ search, status, page, page_size: PAGE_SIZE }).then(
      (res) => {
        if (!alive) return;
        setRecords(res.items);
        setTotal(res.total);
      },
      (e) => alive && setError(e?.body?.message ?? '加载失败'),
    );
    return () => {
      alive = false;
    };
  }, [search, status, page]);

  const fmtTime = (iso: string) => {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const columns: DataColumn<HistoryRecord>[] = [
    { key: 'session_id', title: '训练 ID', width: 150, render: (r) => <span className="mono">{r.session_id}</span> },
    { key: 'created_at', title: '训练时间', width: 150, render: (r) => <span className="num-cell">{fmtTime(r.created_at)}</span> },
    { key: 'direction', title: '训练方向', render: (r) => directionLabel(r.direction) },
    { key: 'language', title: '语言', render: (r) => LANGUAGE_LABELS[r.language] },
    {
      key: 'progress',
      title: '轮次进度',
      render: (r) => {
        const done = r.summaries.reduce((s, x) => s + x.rounds_done, 0);
        const totalR = r.summaries.reduce((s, x) => s + x.target_rounds, 0);
        return <span className="num-cell">{`${done} / ${totalR}`}</span>;
      },
    },
    {
      key: 'status',
      title: '状态',
      render: (r) => <SessionStatusBadge status={r.status} />,
    },
    {
      key: 'actions',
      title: '操作',
      width: 150,
      render: (r) =>
        r.status === 'finished' ? (
          <button className="btn btn-ghost btn-sm" style={{ color: 'var(--primary)' }} onClick={() => navigate(`/report/${r.session_id}`)}>
            查看报告
          </button>
        ) : (
          <button className="btn btn-outline btn-sm" onClick={() => navigate(`/training/${r.session_id}`)}>
            继续训练
          </button>
        ),
    },
  ];

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <DashboardLayout>
      <div className="page">
        <div className="card">
          <div className="card-head">
            <div className="toolbar" style={{ flex: 1 }}>
              <input
                className="input"
                style={{ maxWidth: 260 }}
                placeholder="搜索训练 ID / 方向 / 语言"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
              />
              <select
                className="select"
                style={{ maxWidth: 132 }}
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setPage(1);
                }}
              >
                {STATUS_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setSearch('');
                  setStatus('all');
                  setPage(1);
                }}
              >
                重置
              </button>
              <span className="spacer" />
              <span className="micro" style={{ marginRight: 2 }}>TOTAL</span>
              <span className="num" style={{ fontSize: 13, fontWeight: 600 }}>{total}</span>
            </div>
          </div>

          <div>
            {error ? (
              <ErrorState message={error} onRetry={() => setPage((p) => p)} />
            ) : records === null ? (
              <LoadingState />
            ) : records.length === 0 ? (
              <EmptyState
                title="没有匹配的训练记录"
                desc="换个关键词或状态试试，也可以去开始一场新训练。"
                action={
                  <button className="btn btn-primary btn-sm" onClick={() => navigate('/training/setup')}>
                    开始新训练
                  </button>
                }
              />
            ) : (
              <DataTable columns={columns} rows={records} rowKey={(r) => r.session_id} />
            )}
          </div>

          {totalPages > 1 && (
            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                alignItems: 'center',
                gap: 8,
                padding: '12px 20px',
                borderTop: '1px solid var(--border-hair)',
              }}
            >
              <button className="btn btn-outline btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                上一页
              </button>
              <span className="mono" style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                {page} / {totalPages}
              </span>
              <button className="btn btn-outline btn-sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
                下一页
              </button>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
