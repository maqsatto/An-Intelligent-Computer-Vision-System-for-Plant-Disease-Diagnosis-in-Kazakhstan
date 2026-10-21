FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
RUN pip install --no-cache-dir uv==0.12.1
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY server ./server
COPY ml/runtime ./ml/runtime
COPY alembic.ini ./
RUN uv sync --frozen --no-dev && useradd --create-home --uid 10001 agrovision && mkdir -p /app/storage/photos /app/artifacts && chown -R agrovision:agrovision /app
USER agrovision
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "agrovision.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
