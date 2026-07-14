FROM python:3.14-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_PYTHON_DOWNLOADS=never

# uv.lock is committed; a non-frozen sync updates it if pyproject changed
# (e.g. the added gRPC deps). Once you regenerate and commit uv.lock, you can
# switch back to `uv sync --frozen --no-dev --no-install-project`.
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
