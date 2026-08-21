# KubeTEE subnet-owner validator image.
# Build context is the REPO ROOT so the vendored bittensor SDK is reachable:
#   docker build -f validator/Dockerfile .
# Optional: --build-arg VERSION=1.1.5  (propagates to KUBETEE_VALIDATOR_VERSION
# and the BT-Validator-Version proxy header / User-Agent).
FROM python:3.14-slim AS base

ARG VERSION=1.1.5

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

# Vendored bittensor v11 SDK (path dependency).
COPY subtensor/sdk/python /opt/bittensor-sdk

RUN pip install --no-cache-dir \
    /opt/bittensor-sdk \
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
