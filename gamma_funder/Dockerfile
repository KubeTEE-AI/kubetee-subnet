# TEE worker only, not the public gateway. Build from this package directory:
# docker buildx build --platform linux/amd64 -t ghcr.io/kubetee-ai/gamma-reconciler:v0.1.0-rc1 .
# The signed GitHub builder produces an immutable tag@sha256 digest before
# measuring the corresponding init-data. This candidate is not activated.
FROM ghcr.io/astral-sh/uv:0.13.7-python3.14-trixie-slim@sha256:e80c05a310400cfc90af00b5b7271ef9ad24816e3265e1162af8a678e1aad099 AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project --python 3.14 --compile-bytecode
COPY worker worker
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --python 3.14 --compile-bytecode --no-editable

# linux/amd64 release bases are verified with registry source manifest pins.
FROM python:3.14.3-slim-trixie@sha256:69f1ba39d930d9510073db2edf85af17f1552a5591b0d56c9e44524532271cae
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/.venv/bin:$PATH" \
    KUBETEE_GAMMA_WORKER=0 KUBETEE_GAMMA_SPEND_ENABLED=0 \
    KUBETEE_GAMMA_FINNEY_SPEND_APPROVED=0 KUBETEE_GAMMA_TEST=0
WORKDIR /app
RUN useradd --system --uid 65532 --home-dir /app --shell /usr/sbin/nologin gamma
COPY --from=builder /app /app
RUN mkdir /secrets && chown gamma:gamma /secrets && chmod 700 /secrets
USER gamma
# Kata/CC init-data supplies AA+CDH KBC bootstrap before this process starts.
# It fetches the CA/client identity into a memory emptyDir using CDH/KBS,
# pins both peer certs, then requires client mTLS before ASGI dispatch.
CMD ["python", "-m", "worker.start"]
