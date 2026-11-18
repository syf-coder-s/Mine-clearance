import type { ReactNode } from 'react';

interface PageHeaderProps {
  /** 页面右上角操作区（页面标题由侧边导航承担，不再重复介绍） */
  extra?: ReactNode;
}

/** 页面操作区：仅保留右侧操作按钮 */
export function PageHeader({ extra }: PageHeaderProps) {
  if (!extra) return null;
  return (
    <div className="page-header">
      <div className="extra">{extra}</div>
    </div>
  );
}
