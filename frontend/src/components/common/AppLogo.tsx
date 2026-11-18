import type { ReactNode } from 'react';

interface AppLogoProps {
  collapsed?: boolean;
  size?: 'sm' | 'md';
}

/** 项目 Logo：盾牌 + 对勾，线性风格；字标下加等宽小字 */
export function AppLogo({ collapsed = false, size = 'md' }: AppLogoProps) {
  const box = size === 'sm' ? 26 : 30;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
      <div
        style={{
          width: box,
          height: box,
          borderRadius: 9,
          display: 'grid',
          placeItems: 'center',
          background: 'linear-gradient(160deg, #F1F5FE, #E4EBFB)',
          border: '1px solid var(--primary-line)',
          color: 'var(--primary)',
          flexShrink: 0,
        }}
      >
        <svg width={box - 12} height={box - 12} viewBox="0 0 32 32" fill="none" aria-hidden>
          <path
            d="M16 3l11 4v9c0 7-4.6 11.6-11 13C9.6 27.6 5 23 5 16V7l11-4z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
          />
          <path d="M11.5 15.5l3 3 6-6.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      {!collapsed && (
        <div style={{ lineHeight: 1.15, minWidth: 0 }}>
          <div style={{ fontSize: 14.5, fontWeight: 600, letterSpacing: '-0.01em', color: 'var(--text-main)' }}>
            排雷兵
          </div>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 9,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              color: 'var(--text-tertiary)',
              marginTop: 3,
            }}
          >
            Mine Clearance
          </div>
        </div>
      )}
    </div>
  );
}

export function AppIcon({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <path
        d="M16 3l11 4v9c0 7-4.6 11.6-11 13C9.6 27.6 5 23 5 16V7l11-4z"
        stroke="var(--primary)"
        strokeWidth="2"
        fill="none"
        strokeLinejoin="round"
      />
      <path d="M12 16l3 3 5.5-6" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  );
}

interface AppIconProps {
  children?: ReactNode;
}
export type { AppIconProps };
