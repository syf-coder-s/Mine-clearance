/** 顶部导航条：左侧面包屑，右侧连接状态 + 刷新 + 用户 */
import { useLocation } from 'react-router-dom';
import { API_BASE_URL, isMockMode } from '../../services/apiClient';
import { useHealth } from '../../app/HealthProvider';
import { IconRefresh, IconChevronRight } from '../icons';

const TITLE_MAP: { match: (p: string) => boolean; title: string; section: string }[] = [
  { match: (p) => p.startsWith('/dashboard'), title: '工作台', section: '训练' },
  { match: (p) => p.startsWith('/training/setup'), title: '开始训练', section: '训练' },
  { match: (p) => p.startsWith('/training/'), title: '训练工作台', section: '训练' },
  { match: (p) => p.startsWith('/history'), title: '训练历史', section: '训练' },
  { match: (p) => p.startsWith('/analytics'), title: '能力分析', section: '洞察' },
  { match: (p) => p.startsWith('/system'), title: '系统状态', section: '洞察' },
  { match: (p) => p.startsWith('/report'), title: '训练报告', section: '报告' },
];

export function Topbar() {
  const { pathname } = useLocation();
  const mock = isMockMode();
  const { health, loading, error, refresh } = useHealth();

  const found = TITLE_MAP.find((t) => t.match(pathname));
  const title = found?.title ?? '排雷兵';
  const section = found?.section ?? '控制台';

  const state = mock
    ? { text: '演示数据', tone: 'is-warn' as const }
    : loading
      ? { text: '检查中', tone: '' as const }
      : error
        ? { text: '后端不可达', tone: 'is-err' as const }
        : health
          ? health.mock_llm
            ? { text: '模型未接入', tone: 'is-warn' as const }
            : { text: `在线 · v${health.schema_version}`, tone: 'is-ok' as const }
          : { text: '检查中', tone: '' as const };

  const apiLabel = API_BASE_URL || '同源（/v1）';
  const tip = health?.mock_llm
    ? '后端模型密钥未接入，当前为内置演示数据（请检查 .env 中的模型配置）'
    : error
      ? `${error}（API：${apiLabel}）`
      : `API 地址：${apiLabel}`;

  return (
    <header className="topbar">
      <div className="crumb">
        <span>{section}</span>
        <IconChevronRight size={11} className="crumb-sep" />
        <b>{title}</b>
      </div>

      <div className="topbar-right">
        <button
          className="btn btn-ghost btn-icon"
          onClick={refresh}
          disabled={loading || mock}
          title="刷新服务状态"
          aria-label="刷新服务状态"
        >
          <IconRefresh size={15} />
        </button>

        <span className={`status-pill ${state.tone}`} title={tip}>
          <span className="dot" />
          {state.text}
        </span>

        <span className="topbar-sep" />

        <div className="user-chip">
          <div className="user-avatar" aria-hidden>
            演
          </div>
          <div className="user-meta">
            <div className="n">演示用户</div>
            <div className="i">demo-user</div>
          </div>
        </div>
      </div>
    </header>
  );
}
