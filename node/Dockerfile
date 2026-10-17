# syntax=docker/dockerfile:1.7

# Pinned uv, copied in as a single static binary.
FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

# Build stage: resolve exactly what uv.lock says into a venv, minus bundled tests and type stubs. Only pyproject.toml and uv.lock
# are bind-mounted, so this layer is rebuilt only when dependencies change, not on code edits.
FROM python:3.12-slim-bookworm AS build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev \
 && find /opt/venv -type d -name tests -prune -exec rm -rf {} + \
 && find /opt/venv -name '*.pyi' -delete

# Runtime stage: same base, no uv, no build cache, no pip cache; just the venv and the source.
FROM python:3.12-slim-bookworm
LABEL org.opencontainers.image.source="https://github.com/rangelovkiril/EDTH" \
      org.opencontainers.image.description="EDTH RPi detection node"
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY src ./src
RUN python -m compileall -q src
ENTRYPOINT ["python", "-m", "src"]
