FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir uv && uv sync --extra web

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "vn_agent.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
