# EduDSS production image — the ONE immutable deployable artifact (C1.2).
#
# Reproducibility:
# - Base pinned by digest. Tag kept for readability: python 3.11.16, Debian 13 (trixie).
#   Do not bump casually; update deliberately and re-run the release gate.
# - Dependencies: requirements.txt (human-maintained direct deps) + requirements.lock.txt
#   (machine-resolved full environment). The build FAILS if the installed set drifts from
#   the lock (see tools/lock_dependencies.py to regenerate after changing requirements.txt).
FROM python:3.11.16-slim-trixie@sha256:da047cb8f9d1d98e5c070f5300ba9f7274e33b8fc0e5be5ed88740aed1b95ba9 AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt requirements.lock.txt /app/

# linux/arm64 (Oracle Cloud Ampere A1 free tier): PyTorch publishes no "+cpu" local-version
# wheel for aarch64; the plain PyPI torch 2.10.0 aarch64 wheel IS the CPU-only build (CUDA
# aarch64 wheels on PyPI start at 2.11). Rewrite that ONE pin in both files; everything else,
# including the lock-drift check below, stays identical to amd64.
RUN if [ "$(uname -m)" = "aarch64" ]; then \
        sed -i 's/^torch==2\.10\.0+cpu/torch==2.10.0/' /app/requirements.txt /app/requirements.lock.txt; \
    fi

RUN python -m venv /opt/edudss-venv \
    && . /opt/edudss-venv/bin/activate \
    && PIP_VERSION="$(sed -n 's/^# pip==//p' /app/requirements.lock.txt)" \
    && python -m pip install --upgrade "pip==${PIP_VERSION}" \
    && python -m pip install -r /app/requirements.txt -c /app/requirements.lock.txt \
    && python -m pip install --no-deps "$(grep -i '^xgboost==' /app/requirements.lock.txt)" \
    && python - <<'PY'
import importlib.metadata as m, platform, re, torch
bad = [d.name for d in m.distributions() if d.name.lower().startswith("nvidia") or d.name.lower() == "triton"]
assert not bad, f"unexpected GPU-only packages installed: {bad}"
assert torch.cuda.is_available() is False, torch.__version__
assert torch.__version__.endswith("+cpu") or platform.machine() == "aarch64", torch.__version__
norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()
skip = {"pip", "setuptools", "wheel"}
lock = {}
for line in open("/app/requirements.lock.txt", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "==" in line:
        name, version = line.split("==", 1)
        lock[norm(name)] = version
installed = {norm(d.metadata["Name"]): d.version for d in m.distributions() if norm(d.metadata["Name"]) not in skip}
drift = sorted(set(lock.items()) ^ set(installed.items()))
assert not drift, f"installed environment drifts from requirements.lock.txt: {drift[:10]}"
print(f"Dependency lock verified: {len(installed)} packages match; CPU-only torch {torch.__version__}")
PY

# LightGBM and other native ML wheels need the OpenMP runtime at import time.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

FROM python:3.11.16-slim-trixie@sha256:da047cb8f9d1d98e5c070f5300ba9f7274e33b8fc0e5be5ed88740aed1b95ba9 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy only the verified runtime environment from the builder stage, excluding
# build-only tooling that is not required at runtime.
COPY --from=builder /opt/edudss-venv /opt/edudss-venv
# C1.2: pip is build tooling too - nothing in the application invokes it at runtime, and
# its vendored components (msgpack, pkg_resources/setuptools, declared in
# pip/_vendor/bom.cdx.json) were the source of 3 HIGH scanner findings. The image is
# immutable (never `pip install` in a running container), so pip is removed from both the
# application venv and the base interpreter.
RUN rm -rf \
    /opt/edudss-venv/lib/python3.11/site-packages/pip \
    /opt/edudss-venv/lib/python3.11/site-packages/pip-*.dist-info \
    /opt/edudss-venv/bin/pip /opt/edudss-venv/bin/pip3 /opt/edudss-venv/bin/pip3.11 \
    /usr/local/lib/python3.11/site-packages/pip \
    /usr/local/lib/python3.11/site-packages/pip-*.dist-info \
    /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11 \
    /usr/local/lib/python3.11/site-packages/setuptools* \
    /usr/local/lib/python3.11/site-packages/wheel* \
    /usr/local/lib/python3.11/site-packages/setuptools-*.dist-info \
    /usr/local/lib/python3.11/site-packages/wheel-*.dist-info \
    /opt/edudss-venv/lib/python3.11/site-packages/setuptools* \
    /opt/edudss-venv/lib/python3.11/site-packages/wheel* \
    /opt/edudss-venv/lib/python3.11/site-packages/setuptools-*.dist-info \
    /opt/edudss-venv/lib/python3.11/site-packages/wheel-*.dist-info \
    && apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    # C1.2 (2026-10-04): Debian security updates for HIGH CVE-2026-84782 (openssl) and
    # HIGH CVE-2026-103111 (pcre2); exact versions pinned for reproducibility.
    && apt-get install -y --no-install-recommends \
        libssl3t64=3.5.7-1~deb13u3 openssl=3.5.7-1~deb13u3 openssl-provider-legacy=3.5.7-1~deb13u3 \
        libpcre2-8-0=10.46-1~deb13u3 \
    && rm -rf /var/lib/apt/lists/*

COPY . /app
# data_warehouse/ is excluded from the build context; create it so a named volume
# mounted there (deploy/production) inherits the non-root owner.
RUN groupadd --system edudss && useradd --system --gid edudss --home-dir /app edudss \
    && mkdir -p /app/data_warehouse /app/uploads \
    && chown -R edudss:edudss /app
USER edudss

# Release identity baked into the image (read by dss/core/release.py; no secrets).
ARG EDUDSS_GIT_SHA=unknown
ARG EDUDSS_BUILD_TIME=unknown
ARG EDUDSS_IMAGE_REF=
ENV EDUDSS_GIT_SHA=${EDUDSS_GIT_SHA} \
    EDUDSS_BUILD_TIME=${EDUDSS_BUILD_TIME} \
    EDUDSS_IMAGE_REF=${EDUDSS_IMAGE_REF}
LABEL org.opencontainers.image.title="EduDSS" \
      org.opencontainers.image.revision="${EDUDSS_GIT_SHA}" \
      org.opencontainers.image.created="${EDUDSS_BUILD_TIME}" \
      org.opencontainers.image.base.name="python:3.11.16-slim-trixie"

ENV PATH="/opt/edudss-venv/bin:${PATH}"
ENV PYTHONPATH=/app
ENV APP_FILE=run_dss.py
ENV STREAMLIT_PORT=8501
ENV EDUDSS_HEALTH_PORT=8081
# Prometheus multiprocess files shared by Streamlit and the health server (/metrics);
# wiped at every start so counters never mix runs.
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/edudss-metrics
# No telemetry to third parties by default, in every environment.
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# 8501 = UI (Streamlit), 8081 = operator endpoints /livez /readyz /version.
EXPOSE 8501 8081

# Liveness only: process + UI server answering. Dependencies are reported by /readyz,
# which orchestration/deploy scripts poll before routing traffic.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('EDUDSS_HEALTH_PORT', '8081') + '/livez', timeout=5)" || exit 1

# Operator endpoints run beside Streamlit; if Streamlit exits, the container exits.
CMD ["sh", "-c", "rm -rf \"$PROMETHEUS_MULTIPROC_DIR\" && mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\" && python ops/write_streamlit_secrets.py && (python -m dss.core.health_server &) && exec streamlit run ${APP_FILE} --server.port=${STREAMLIT_PORT} --server.address=0.0.0.0 --server.headless=true"]
