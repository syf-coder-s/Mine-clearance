/**
 * 全局健康状态源：Topbar / 首页 / 系统页共用 GET /v1/health 的结果。
 * 不做自动轮询；系统页提供手动刷新入口。
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { getHealth } from '../services/systemService';
import type { SystemHealth } from '../mocks/systemMock';

interface HealthContextValue {
  health: SystemHealth | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const HealthContext = createContext<HealthContextValue | null>(null);

/** 把请求异常转成可读中文：优先取后端错误体的 message */
function readableHealthError(err: unknown): string {
  if (err && typeof err === 'object' && 'body' in err) {
    const body = (err as { body?: { message?: unknown } }).body;
    if (body && typeof body.message === 'string' && body.message) return body.message;
  }
  return '无法连接后端，请确认 8010 服务已启动';
}

export function HealthProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // 请求序号：快速重复刷新时，旧请求的结果不得覆盖新请求
  const seqRef = useRef(0);

  // 挂载时请求一次；状态落点全部在异步回调里，effect 内不做同步 setState
  useEffect(() => {
    const seq = ++seqRef.current;
    let alive = true;
    getHealth().then(
      (next) => {
        if (!alive || seqRef.current !== seq) return;
        setHealth(next);
        setError(null);
        setLoading(false);
      },
      (e) => {
        if (!alive || seqRef.current !== seq) return;
        setHealth(null);
        setError(readableHealthError(e));
        setLoading(false);
      },
    );
    return () => {
      alive = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    const seq = ++seqRef.current;
    setLoading(true);
    setError(null);
    try {
      const next = await getHealth();
      if (seqRef.current !== seq) return;
      setHealth(next);
      setError(null);
    } catch (e) {
      if (seqRef.current !== seq) return;
      setHealth(null);
      setError(readableHealthError(e));
    } finally {
      if (seqRef.current === seq) setLoading(false);
    }
  }, []);

  return (
    <HealthContext.Provider value={{ health, loading, error, refresh }}>
      {children}
    </HealthContext.Provider>
  );
}

export function useHealth(): HealthContextValue {
  const ctx = useContext(HealthContext);
  if (!ctx) throw new Error('useHealth 必须在 HealthProvider 内使用');
  return ctx;
}