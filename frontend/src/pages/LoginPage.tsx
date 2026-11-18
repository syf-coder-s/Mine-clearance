import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { AuthLayout } from '../layouts/AuthLayout';
import { AppIcon } from '../components/common/AppLogo';
import { trackSpotlight } from '../utils/spotlight';

const DEMO_ACCOUNT = '123456';
const DEMO_PASSWORD = '123456';

/** 登录页：仅在前端校验演示账号，不发起认证请求 */
export function LoginPage() {
  const navigate = useNavigate();
  const [account, setAccount] = useState(DEMO_ACCOUNT);
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [error, setError] = useState('');

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!account.trim() || !password) {
      setError('请输入账号和密码');
      return;
    }
    if (account.trim() !== DEMO_ACCOUNT || password !== DEMO_PASSWORD) {
      setError('账号或密码错误，请使用演示账号登录');
      return;
    }

    setError('');
    navigate('/dashboard');
  }

  return (
    <AuthLayout>
      <div className="card card-spotlight auth-card" onMouseMove={trackSpotlight}>
        <div className="auth-card-head">
          <div className="auth-card-icon"><AppIcon size={26} /></div>
          <div>
            <h2>欢迎回来</h2>
            <p>登录排雷兵训练平台</p>
          </div>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <label className="field">
            <span className="field-label">账号</span>
            <input
              className="input"
              value={account}
              onChange={(event) => {
                setAccount(event.target.value);
                setError('');
              }}
              placeholder="请输入账号"
              autoComplete="username"
              autoFocus
            />
          </label>

          <label className="field">
            <span className="field-label">密码</span>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
                setError('');
              }}
              placeholder="请输入密码"
              autoComplete="current-password"
            />
          </label>

          {error && <div className="auth-error" role="alert">{error}</div>}

          <button className="btn btn-primary btn-lg auth-submit" type="submit">
            登录
          </button>
        </form>
      </div>
    </AuthLayout>
  );
}
