/**
 * 统一 API 客户端
 *
 * 数据模式由环境变量切换：
 *   VITE_DATA_MODE=mock        → 使用内置 Mock 数据
 *   未配置 / 空字符串 / 其他值  → live，请求真实后端（默认）
 *
 * 默认 live：交付时即使漏配 .env 也不会悄悄变成演示模式；
 * 要跑演示必须显式设置 VITE_DATA_MODE=mock（npm run dev:mock 已内置）。
 *
 *   VITE_API_BASE_URL          → 真实后端地址，默认空串（同源，页面直接请求 /v1）；
 *                                本地开发连 http://localhost:8010 时需显式配置（走 CORS）。
 *
 * 注意：真实 API Key 只放在后端 .env，前端永远不配置、不读取任何 Key。
 */
import type { ApiError } from '../types/api';

/** 只有显式 VITE_DATA_MODE === 'mock' 才是 mock，其余（未配/空串/拼错）一律 live */
export const DATA_MODE: 'mock' | 'live' =
  import.meta.env.VITE_DATA_MODE === 'mock' ? 'mock' : 'live';

/** 去掉首尾空格与末尾斜杠，避免拼出 //v1 这类地址；空串保持空串（同源请求） */
function normalizeBase(base: string): string {
  return base.trim().replace(/\/+$/, '');
}

export const API_BASE_URL: string = normalizeBase(
  import.meta.env.VITE_API_BASE_URL ?? '',
);

export function isMockMode(): boolean {
  return DATA_MODE !== 'live';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    let body: { error?: string; detail?: string; message?: string };
    try {
      body = await res.json();
    } catch {
      body = {};
    }
    // 真实后端错误体为 { error, detail }；统一收敛成前端约定的 { code, message }
    const err: ApiError = {
      status: res.status,
      body: {
        code: body?.error ?? 'UNKNOWN',
        message: body?.detail ?? body?.message ?? res.statusText,
      },
    };
    throw err;
  }
  return (await res.json()) as T;
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, payload?: unknown) =>
    request<T>(path, { method: 'POST', body: payload ? JSON.stringify(payload) : undefined }),
};