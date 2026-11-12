# KubeTEE subnet-owner validator image.
# Build context is the REPO ROOT (docker build -f validator/Dockerfile .).
# The `subtensor/` submodule is NOT needed at build time -- it is the chain
# source reference; the Python SDK comes from the official PyPI release.
# Optional: --build-arg VERSION=1.1.6  (propagates to KUBETEE_VALIDATOR_VERSION
# and the BT-Validator-Version proxy header / User-Agent).
FROM python:3.15-slim AS base

ARG VERSION=1.4.2

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    KUBETEE_VALIDATOR_VERSION=${VERSION}

WORKDIR /app

# System deps first (rarely change, so cached at the bottom of the stack).
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# Official PyPI SDK matching subtensor v488. Pin the SDK and its native core
# together: v488 requires bittensor-core>=0.1.9 for its cryptographic APIs.
# Published wheels avoid a Rust source build from the vendored SDK.
RUN pip install --no-cache-dir \
    "bittensor==11.3.2" \
    "bittensor-core==0.1.9" \
    "httpx>=0.27" \
    "prometheus-client>=0.20"

# Validator modules copied flat into /app (the directory is a flat unit of
# bare-import modules, not a package). Placed last so validator code changes
# invalidate only this layer + the user setup below.
COPY validator/*.py /app/

# Run as a non-root user (the validator handles a hotkey seed and bearer tokens
# in env; a container escape should not get root).
RUN useradd -r -m -d /home/kubetee -u 10001 -g nogroup kubetee \
    && mkdir -p /home/kubetee/.kubetee \
    && chown -R kubetee:nogroup /app /home/kubetee
USER kubetee

# Default command — deployments can override (e.g. with --env-file, ONCE, DRY_RUN).
CMD ["python", "validator.py"]
