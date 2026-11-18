﻿﻿﻿import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DashboardLayout } from '../layouts/DashboardLayout';
import { createSession } from '../services/trainingService';
import { isMockMode } from '../services/apiClient';
import type { Language, TrainingDirection } from '../types/training';

const LANGUAGES: { value: Language; label: string; desc: string; supported: boolean }[] = [
  { value: 'python', label: 'Python', desc: '当前唯一支持语言', supported: true },
  { value: 'java', label: 'Java', desc: '待后端确认', supported: false },
  { value: 'c', label: 'C', desc: '待后端确认', supported: false },
  { value: 'cpp', label: 'C++', desc: '待后端确认', supported: false },
];

const DIRECTIONS: { value: TrainingDirection; label: string; desc: string }[] = [
  { value: 'random', label: '随机训练', desc: '混合各类问题' },
  { value: 'logic_boundary', label: '逻辑与边界问题', desc: '边界条件、循环不变量等' },
  { value: 'api_usage', label: 'API 使用问题', desc: '接口语义与返回值' },
  { value: 'security_performance', label: '安全与性能问题', desc: '待后端确认' },
];

/** 训练配置页：选择语言与方向；题量/轮数/预算为固定规则 */
export function TrainingSetupPage() {
  const navigate = useNavigate();
  const mock = isMockMode();
  const [language, setLanguage] = useState<Language>('python');
  const [direction, setDirection] = useState<TrainingDirection>('random');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setCreating(true);
    setError(null);
    try {
      const session = await createSession(language, direction);
      navigate(`/training/${session.session_id}`);
    } catch {
      setError('创建训练失败，请确认后端服务已启动后重试');
      setCreating(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="page">
        {/* 语言 */}
        <div className="card card-pad">
          <div className="card-title">训练语言</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginTop: 12 }}>
            {LANGUAGES.map((l) => (
              <button
                key={l.value}
                onClick={() => setLanguage(l.value)}
                disabled={!l.supported}
                style={{
                  padding: '12px 10px',
                  textAlign: 'left',
                  borderRadius: 'var(--radius-control)',
                  border: language === l.value ? '1.5px solid var(--primary)' : '1px solid var(--border)',
                  background: language === l.value ? 'var(--primary-soft)' : 'var(--bg-card)',
                  cursor: l.supported ? 'pointer' : 'not-allowed',
                  opacity: l.supported ? 1 : 0.55,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 600 }}>{l.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>{l.desc}</div>
                {!l.supported && (
                  <div style={{ marginTop: 6 }}>
                    <span className="badge badge-neutral">暂未支持</span>
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* 方向 */}
        <div className="card card-pad">
          <div className="card-title">训练方向</div>
          {mock ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginTop: 12 }}>
                {DIRECTIONS.map((d) => (
                  <button
                    key={d.value}
                    onClick={() => setDirection(d.value)}
                    style={{
                      padding: '12px 14px',
                      textAlign: 'left',
                      borderRadius: 'var(--radius-control)',
                      border: direction === d.value ? '1.5px solid var(--primary)' : '1px solid var(--border)',
                      background: direction === d.value ? 'var(--primary-soft)' : 'var(--bg-card)',
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{d.label}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>{d.desc}</div>
                    </div>
                    {direction === d.value && <span style={{ color: 'var(--primary)', fontWeight: 700 }}>✓</span>}
                  </button>
                ))}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 12 }}>
                演示模式：方向用于筛选本地题库，题量不足时会补充其他方向题目。
              </div>
            </>
          ) : (
            <div
              style={{
                marginTop: 12,
                padding: '12px 14px',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-control)',
                background: 'var(--bg-card)',
                fontSize: 12,
                color: 'var(--text-secondary)',
                lineHeight: 1.7,
              }}
            >
              当前后端使用内置题单出题（Python），训练方向暂未接入；接入 specs 后开放。
            </div>
          )}
        </div>

        {/* 规则说明 */}
        <div className="card card-pad">
          <div className="card-title">训练规则</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginTop: 12 }}>
            {[
              ['3 道题', '每次训练固定的题目数量，不可修改'],
              ['每题最多 3 轮', '实际轮次以开局题面为准'],
              ['12 次调用', '每场在线模型调用上限（含 3 次结算预留）'],
            ].map(([t, d]) => (
              <div key={t} style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 'var(--radius-control)' }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--primary)' }}>{t}</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>{d}</div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 12 }}>
            结算前不会展示正确答案、缺陷位置、触发条件与修复方案。
          </div>
        </div>

        {error && (
          <div className="card card-pad" style={{ borderColor: 'var(--danger)', color: 'var(--danger)', fontSize: 13 }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button className="btn btn-outline btn-lg" onClick={() => navigate('/dashboard')}>
            取消
          </button>
          <button className="btn btn-primary btn-lg" onClick={start} disabled={creating}>
            {creating ? (mock ? '创建中…' : 'AI 出题中，约需 1 分钟，请勿关闭页面…') : '开始训练'}
          </button>
        </div>
      </div>
    </DashboardLayout>
  );
}

