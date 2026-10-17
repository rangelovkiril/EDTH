# syntax=docker/dockerfile:1.7
# Runtime for the Raspberry Pi node (arm64). libcamera and picamera2 come from Raspberry Pi's apt
# repo, the same one the host OS uses, so the userspace matches the kernel's camera drivers.

FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

FROM debian:trixie-slim AS base
# rpi-archive-keyring.pgp is Raspberry Pi's public archive key (fingerprint
# CF8A1AF502A2AA2D763BAE7E82B129927FA3303E), copied from /usr/share/keyrings on Raspberry Pi OS.
# The copy on their website is stale: apt's sqv rejects it for lack of a current binding signature.
COPY rpi-archive-keyring.pgp /usr/share/keyrings/raspberrypi-archive-keyring.pgp
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
 && printf 'Types: deb\nURIs: http://archive.raspberrypi.com/debian/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/raspberrypi-archive-keyring.pgp\n' \
      > /etc/apt/sources.list.d/raspi.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-numpy python3-picamera2 libcamera-ipa

# Build stage: the locked pip dependencies go into a venv that also sees the apt packages above.
# numpy comes from apt (picamera2 depends on it), so there is exactly one numpy in the image.
# Only pyproject.toml and uv.lock are bind-mounted: this layer is rebuilt only when they change.
FROM base AS build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/bin/python3 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv venv --system-site-packages /opt/venv \
 && uv sync --locked --no-dev --no-install-package numpy \
 && find /opt/venv -type d -name tests -prune -exec rm -rf {} + \
 && find /opt/venv -name '*.pyi' -delete

FROM base
ARG GIT_SHA=dev
LABEL org.opencontainers.image.source="https://github.com/rangelovkiril/EDTH" \
      org.opencontainers.image.description="EDTH RPi detection node" \
      org.opencontainers.image.revision="${GIT_SHA}"
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    EDTH_VERSION=${GIT_SHA}
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY src ./src
RUN python -m compileall -q src
ENTRYPOINT ["python", "-m", "src"]
