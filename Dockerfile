FROM python:3.11-slim

WORKDIR /app

# Dependencies first for layer caching
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --extra web

# Source + frontend + config
COPY src/ src/
COPY frontend/ frontend/
COPY config/ config/

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "vn_agent.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
