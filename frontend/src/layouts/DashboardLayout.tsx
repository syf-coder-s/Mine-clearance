import type { ReactNode } from 'react';
import { Sidebar } from '../components/common/Sidebar';
import { Topbar } from '../components/common/Topbar';

/** 登录后公共布局：顶部 60px + 左侧 232px + 内容区 24px */
export function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <Topbar />
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}
