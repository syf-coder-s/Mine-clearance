"""同源托管前端打包产物（可选，dist 不存在时后端仍是纯 API）。

「前后端同源」部署：前端以 VITE_API_BASE_URL=''（空串）构建，页面直接请求
/v1/*，不产生跨域，也不依赖 CORS 白名单。后端在所有 API 路由之后挂一个 SPA
兜底路由，把 /dashboard、/report/xxx 这类前端路由回退到 index.html。

dist 目录查找顺序：FRONTEND_DIST_DIR 环境变量 > 仓库根 frontend/dist >
容器内 /app/frontend/dist。找不到 index.html 时本模块什么都不挂。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# API 路由前缀：命中该前缀但没匹配到具体路由时，应返回 404 而不是 index.html。
_API_PREFIX = "v1"


def resolve_dist(dist_dir: Optional[str] = None) -> Optional[Path]:
    """定位前端 dist；找不到 index.html 返回 None。"""
    if dist_dir:
        candidate = Path(dist_dir)
        return candidate if (candidate / "index.html").is_file() else None

    repo_root = Path(__file__).resolve().parents[3]  # .../src/mineclearance/api/ -> 仓库根
    for candidate in (repo_root / "frontend" / "dist", Path("/app/frontend/dist")):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """挂载 assets/fonts 静态目录，并注册 SPA 兜底路由。"""
    for sub in ("assets", "fonts"):
        path = dist / sub
        if path.is_dir():
            app.mount(f"/{sub}", StaticFiles(directory=str(path)), name=f"frontend-{sub}")

    root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa(full_path: str) -> FileResponse:
        # /v1 开头的未知路径是 API 404，不能吐 index.html。
        if full_path == _API_PREFIX or full_path.startswith(_API_PREFIX + "/"):
            raise HTTPException(status_code=404)
        target = (dist / full_path).resolve()
        if full_path and target.is_file() and target.is_relative_to(root):
            return FileResponse(target)
        return FileResponse(dist / "index.html")
