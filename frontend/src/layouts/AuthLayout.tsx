import { useState, type ReactNode } from 'react';
import { AppLogo } from '../components/common/AppLogo';

/** 登录页布局：顶部品牌栏、精简品牌介绍与登录卡片 */
export function AuthLayout({ children }: { children: ReactNode }) {
  const [showAccountInfo, setShowAccountInfo] = useState(false);

  return (
    <div className="auth-shell">
      <header className="auth-header">
        <AppLogo />
        <div className="auth-account">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            aria-expanded={showAccountInfo}
            aria-controls="auth-account-info"
            onClick={() => setShowAccountInfo((visible) => !visible)}
          >
            账号设置
          </button>
          {showAccountInfo && (
            <div className="auth-account-info card" id="auth-account-info">
              <strong>演示账号</strong>
              <span>账号与密码均为 <code>123456</code></span>
              <small>纯前端演示，暂不支持修改账号。</small>
            </div>
          )}
        </div>
      </header>

      <main className="auth-main">
        <section className="auth-intro">
          <div className="micro">CODE REVIEW · ADVERSARIAL TRAINING</div>
          <h1>
            在代码审查对抗中，
            <br />
            练出「排雷」的本事
          </h1>
          <p>阅读代码、定位缺陷、提交修复，在多轮对抗中提升代码审查能力。</p>
        </section>

        <section className="auth-form-panel" aria-label="账号登录">
          {children}
        </section>
      </main>

      <footer className="auth-footer micro">MINE CLEARANCE · FRONTEND DEMO</footer>
    </div>
  );
}
