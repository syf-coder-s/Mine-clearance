# ---- 前端构建阶段：在容器内跑 npm，部署机器无需预装 Node ----
FROM node:24-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 运行阶段 ----
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY tests ./tests
COPY scripts ./scripts
COPY --from=frontend /fe/dist ./frontend/dist
RUN useradd --create-home --uid 10001 mineclearance && mkdir -p /app/data && chown mineclearance /app/data
USER mineclearance
EXPOSE 8010
CMD ["python", "-m", "uvicorn", "mineclearance.api.main:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
