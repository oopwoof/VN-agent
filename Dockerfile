# Stage 1: Build React frontend
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + built frontend
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN pip install --no-cache-dir uv && uv sync --extra web --no-dev
COPY --from=frontend /app/frontend/dist frontend/dist
COPY config/ config/

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "vn_agent.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
