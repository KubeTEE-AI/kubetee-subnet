# KubeTEE subnet-owner validator image.
# Build context is the REPO ROOT so the vendored bittensor SDK is reachable:
#   docker build -f validator/Dockerfile .
# Optional: --build-arg VERSION=1.1.6  (propagates to KUBETEE_VALIDATOR_VERSION
# and the BT-Validator-Version proxy header / User-Agent).

########################################################################
# Stage 1 -- build the vendored bittensor SDK and its Rust core.
#
# The vendored SDK (subtensor/sdk/python) depends on `bittensor-core`,
# a maturin/PyO3 crate living in the SAME subtensor workspace
# (subtensor/sdk/bittensor-core-py). PyPI has no stable
# `bittensor-core>=0.1.6` wheel -- 0.1.5 is the newest stable and 0.1.6
# exists only as release candidates -- so `pip install` of the SDK fails
# with "No matching distribution found for bittensor-core<0.2.0,>=0.1.6".
# `uv` honours the SDK's `[tool.uv.sources]` (`path = "../bittensor-core-py"`)
# and builds that crate from source. Hence uv, not pip, in this stage.
########################################################################
FROM python:3.14-slim AS sdk-build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Toolchain for the maturin build. `openssl` is built vendored and
# `sodiumoxide` compiles C, so a C toolchain plus perl (openssl's
# Configure) is required; pkg-config for the rust build scripts.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        perl \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# rustup without a default toolchain: subtensor/rust-toolchain.toml pins
# the channel (1.89) and cargo selects it automatically.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --profile minimal --default-toolchain none \
    && . /root/.cargo/env
ENV PATH=/root/.cargo/bin:$PATH

# The SDK's `bittensor-core` is `path = "../bittensor-core-py"`, a member of
# the subtensor Cargo workspace -- the workspace manifest and every crate it
# names must be present for cargo to resolve the graph. Copy the whole tree
# (`.git` is excluded by .dockerignore).
COPY subtensor /build/subtensor

# Cache the cargo registry and the workspace target dir across builds: the
# first build clones polkadot-sdk and compiles the sp-core tree; repeats are
# incremental instead of from scratch.
RUN --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    --mount=type=cache,target=/build/subtensor/target \
    uv venv /opt/venv --python 3.14 \
    && VIRTUAL_ENV=/opt/venv uv pip install \
        --python /opt/venv/bin/python \
        /build/subtensor/sdk/python \
        "httpx>=0.27" \
        "prometheus-client>=0.20"

########################################################################
# Stage 2 -- runtime.
########################################################################
FROM python:3.14-slim AS base

ARG VERSION=1.1.6

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    KUBETEE_VALIDATOR_VERSION=${VERSION} \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

# System deps first (rarely change, so cached at the bottom of the stack).
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# The venv built above already carries the vendored bittensor SDK (and its
# compiled Rust extension) plus httpx and prometheus-client. It sits at the
# same absolute path in both stages (both are python:3.14-slim), so the
# interpreter symlink and script shebangs resolve.
COPY --from=sdk-build /opt/venv /opt/venv

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
