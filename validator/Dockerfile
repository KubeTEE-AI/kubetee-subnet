# KubeTEE subnet-owner validator image.
# Build context is the REPO ROOT (docker build -f validator/Dockerfile .).
# The `subtensor/` submodule is NOT needed at build time -- it is the chain
# source reference; the Python SDK comes from the official PyPI release.
# Optional: --build-arg VERSION=1.1.6  (propagates to KUBETEE_VALIDATOR_VERSION
# and the BT-Validator-Version proxy header / User-Agent).
FROM python:3.14-slim AS base

ARG VERSION=1.1.6

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

# Official PyPI bittensor SDK. NOT the vendored subtensor/sdk/python tree:
# that copy carries a `11.x.y.dev0` version and (from subtensor v478) a
# `bittensor-core>=0.1.6` dep with no stable PyPI wheel, so pip cannot
# install it. 11.3.0 is the newest official stable and pulls the prebuilt
# `bittensor-core==0.1.5` wheel -- no Rust toolchain, no source build.
RUN pip install --no-cache-dir \
    "bittensor==11.3.0" \
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
