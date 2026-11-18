#!/usr/bin/env python3
"""
前端 dist 静态服务器（只用 Python 标准库，不需要 Node / pip 包）。

给不方便装 Node 的同事直接跑构建好的 frontend/dist：

    python serve.py               # 默认 http://127.0.0.1:5173
    python serve.py --port 5173
    python serve.py --host 0.0.0.0 --port 5173   # 局域网访问（注意后端 CORS）

说明：
- 默认只绑定 127.0.0.1；需要局域网访问时用 --host 0.0.0.0，
  并让后端把对应地址加进 MC_CORS_ORIGINS。
- 端口默认 5173 是为了匹配后端默认 CORS 白名单
  （http://localhost:5173 与 http://127.0.0.1:5173）。
- 本服务不做 API 代理；前端页面直接按构建时写死的
  VITE_API_BASE_URL 请求后端（默认 http://localhost:8010）。
- SPA fallback：无扩展名的路径（/dashboard、/system、/report/xxx 等）
  文件不存在时返回 index.html；/assets/xxx.js 这类带扩展名但
  不存在的文件返回 404，不返回 index.html。
"""
import argparse
import http.server
import os
import socketserver
import sys

# dist 目录：与本文件同目录下的 dist/
DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")


class SPAHandler(http.server.SimpleHTTPRequestHandler):
    """在 SimpleHTTPRequestHandler 之上补一个 SPA fallback。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST, **kwargs)

    def do_GET(self):  # noqa: N802（沿用标准库命名）
        # 去掉 query / fragment，只看路径本身
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        # 无扩展名 → 视为前端路由：文件不存在或指向目录时回退到 index.html
        has_ext = os.path.splitext(path)[1] != ""
        if not has_ext:
            full = os.path.normpath(os.path.join(DIST, path.lstrip("/")))
            if not os.path.isfile(full):
                self.path = "/index.html"
        # 带扩展名且不存在 → 交给父类正常返回 404
        super().do_GET()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        description="前端 dist 静态服务器（仅标准库，SPA fallback，不做 API 代理）"
    )
    ap.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    ap.add_argument("--port", type=int, default=5173, help="监听端口（默认 5173，匹配后端 CORS 白名单）")
    args = ap.parse_args()

    if not os.path.isdir(DIST):
        print(f"错误：找不到 dist 目录：{DIST}", file=sys.stderr)
        print("请先在 frontend 目录执行 npm run build 生成 dist。", file=sys.stderr)
        sys.exit(1)

    with socketserver.ThreadingTCPServer((args.host, args.port), SPAHandler) as httpd:
        print(f"前端静态服务已启动：http://{args.host}:{args.port}")
        print(f"服务目录：{DIST}")
        print("说明：端口默认 5173 匹配后端默认 CORS 白名单；本服务不做 API 代理。")
        print("按 Ctrl+C 停止。")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止。")


if __name__ == "__main__":
    main()
