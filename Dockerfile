FROM python:3.11-slim

WORKDIR /app

# Copy source + deps together (hatchling needs src/ to build the package)
COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN pip install --no-cache-dir uv && uv sync --extra web --no-dev

# Frontend + config (separate layer for faster rebuilds)
COPY frontend/ frontend/
COPY config/ config/

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "vn_agent.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
