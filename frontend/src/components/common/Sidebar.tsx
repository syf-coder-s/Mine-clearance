import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';
import { AppLogo } from './AppLogo';
import { IconGrid, IconPlus, IconList, IconChart, IconPulse } from '../icons';
import { isMockMode } from '../../services/apiClient';

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
}

const GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: '训练',
    items: [
      { to: '/dashboard', label: '工作台', icon: <IconGrid size={16} /> },
      { to: '/training/setup', label: '开始训练', icon: <IconPlus size={16} /> },
      { to: '/history', label: '训练历史', icon: <IconList size={16} /> },
    ],
  },
  {
    title: '洞察',
    items: [
      { to: '/analytics', label: '能力分析', icon: <IconChart size={16} /> },
      { to: '/system', label: '系统状态', icon: <IconPulse size={16} /> },
    ],
  },
];

/** 左侧导航：232px，白底，选中态用左侧 2px 主色标记 */
export function Sidebar() {
  const mock = isMockMode();

  return (
    <aside className="sb">
      <div className="sb-brand">
        <NavLink to="/dashboard" className="sb-brand-link">
          <AppLogo />
        </NavLink>
      </div>

      <nav className="sb-nav">
        {GROUPS.map((g) => (
          <div key={g.title} className="sb-group">
            <div className="sb-group-title micro">{g.title}</div>
            {g.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => (isActive ? 'sb-link is-active' : 'sb-link')}
              >
                <span className="sb-ico">{item.icon}</span>
                <span className="sb-label">{item.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="sb-foot">
        <span className={mock ? 'dot dot-warning' : 'dot dot-success'} />
        <span className="sb-foot-text">{mock ? '演示模式 · 本地数据' : '已连接后端'}</span>
      </div>
    </aside>
  );
}
