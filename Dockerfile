# Multi-stage build: frontend (Vite/React) then backend (FastAPI)

###############
# Frontend build
###############
FROM node:20-alpine AS frontend
WORKDIR /app/frontend

# Use pnpm (via corepack) to install with lockfile
COPY frontend/package.json frontend/pnpm-lock.yaml ./ 
RUN corepack enable pnpm && pnpm install --frozen-lockfile

COPY frontend/ .
RUN pnpm run build

###############
# Backend runtime
###############
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Copy built frontend assets
COPY --from=frontend /app/frontend/dist /app/frontend/dist

ENV APP_ENV=prod \
    PORT=8000
EXPOSE 8000

CMD ["uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000"]
