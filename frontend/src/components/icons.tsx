import type { SVGProps } from 'react';

/**
 * 线性图标集（1.75px 描边，24 视窗）
 * 只用一套：Sidebar、卡片标题、空态、按钮里都复用，保证风格一致。
 */
type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Base({ size = 16, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconGrid = (p: IconProps) => (
  <Base {...p}>
    <rect x="3" y="3" width="7" height="7" rx="1.6" />
    <rect x="14" y="3" width="7" height="7" rx="1.6" />
    <rect x="3" y="14" width="7" height="7" rx="1.6" />
    <rect x="14" y="14" width="7" height="7" rx="1.6" />
  </Base>
);

export const IconPlus = (p: IconProps) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v8M8 12h8" />
  </Base>
);

export const IconList = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 6h16M4 12h16M4 18h10" />
  </Base>
);

export const IconChart = (p: IconProps) => (
  <Base {...p}>
    <path d="M3 3v18h18" />
    <path d="m7 14 3.5-4.5 3 3L19 6" />
  </Base>
);

export const IconPulse = (p: IconProps) => (
  <Base {...p}>
    <path d="M22 12h-4l-3 8-5-16-3 8H2" />
  </Base>
);

export const IconShield = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <path d="m9 12 2 2 4-4" />
  </Base>
);

export const IconRefresh = (p: IconProps) => (
  <Base {...p}>
    <path d="M21 12a9 9 0 1 1-2.64-6.36" />
    <path d="M21 3v5h-5" />
  </Base>
);

export const IconCheck = (p: IconProps) => (
  <Base {...p}>
    <path d="m5 13 4 4L19 7" />
  </Base>
);

export const IconChevronRight = (p: IconProps) => (
  <Base {...p}>
    <path d="m9 5 7 7-7 7" />
  </Base>
);

export const IconCode = (p: IconProps) => (
  <Base {...p}>
    <path d="m9 18-6-6 6-6M15 6l6 6-6 6" />
  </Base>
);

/** 机器人头像：AI/对抗场景标识（避免放射线形似加载转圈） */
export const IconBot = (p: IconProps) => (
  <Base {...p}>
    <circle cx="12" cy="4.5" r="1.25" />
    <path d="M12 5.75V8" />
    <rect x="5" y="8" width="14" height="11" rx="3.5" />
    <path d="M9.5 12.5h.01M14.5 12.5h.01" />
    <path d="M9.5 15.5h5" />
  </Base>
);

export const IconArrowUpRight = (p: IconProps) => (
  <Base {...p}>
    <path d="M7 17 17 7M9 7h8v8" />
  </Base>
);

export const IconDotDot = (p: IconProps) => (
  <Base {...p}>
    <circle cx="5" cy="12" r="1" />
    <circle cx="12" cy="12" r="1" />
    <circle cx="19" cy="12" r="1" />
  </Base>
);
