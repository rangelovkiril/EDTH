# syntax=docker/dockerfile:1.7
# Ground-side fusion (amd64 for the cluster, arm64 so it can also run on a Pi or a laptop).

FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

FROM python:3.13-slim AS build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev

FROM python:3.13-slim
ARG GIT_SHA=dev
LABEL org.opencontainers.image.source="https://github.com/rangelovkiril/EDTH" \
      org.opencontainers.image.description="EDTH fusion: node bearings to 3D tracks" \
      org.opencontainers.image.revision="${GIT_SHA}"
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    EDTH_VERSION=${GIT_SHA}
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY src ./src
RUN python -m compileall -q src
USER 65534:65534
ENTRYPOINT ["python", "-m", "src"]
