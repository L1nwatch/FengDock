# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=.venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -Ls https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY vendor/TriggerToDo/pyproject.toml vendor/TriggerToDo/uv.lock ./vendor/TriggerToDo/
RUN cd /app/vendor/TriggerToDo && UV_PROJECT_ENVIRONMENT=.venv uv sync --frozen --no-dev

COPY app ./app
COPY vendor/TriggerToDo/app ./vendor/TriggerToDo/app
COPY index.html ./index.html
COPY static ./static
COPY tools ./tools
COPY scripts ./scripts

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv

WORKDIR /app

COPY --from=builder /app/.venv ${VIRTUAL_ENV}
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

COPY app ./app
COPY --from=builder /app/vendor/TriggerToDo/.venv ./vendor/TriggerToDo/.venv
COPY vendor/TriggerToDo/app ./vendor/TriggerToDo/app
COPY index.html ./index.html
COPY static ./static
COPY tools ./tools
COPY scripts ./scripts
COPY pyproject.toml uv.lock ./

EXPOSE 8000
EXPOSE 8001
CMD ["python", "scripts/run_servers.py"]
