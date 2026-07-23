# Dockerfile for KubeTEE validator (and stub miners)
# Builds a container using uv (as requested) + current requirements + the subnet code
# For v11 Bittensor (unified package from subtensor)

FROM python:3.13-slim

WORKDIR /app

# System deps for bittensor / substrate
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libssl-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

COPY requirements.txt .

# Install CPU-only torch first. The validator needs no GPU (see CLAUDE.md), so the
# default CUDA wheels (~2.8GB) are pure waste and overflow CI runner disk. Pinning
# the CPU index means requirements.txt's `torch>=2` is already satisfied below.
RUN uv pip install --system --no-cache torch --index-url https://download.pytorch.org/whl/cpu

# Use uv for installation (recommended for the project)
RUN uv pip install --system --no-cache -r requirements.txt

# btcli is bundled by bittensor>=11.0.0.dev0 (unified SDK from RaoFoundation/subtensor).
# If downgrading to a pre-unified release, add `bittensor-cli` to requirements.txt.

# Make sure /usr/local/bin is in PATH (uv --system puts scripts there)
ENV PATH="/usr/local/bin:${PATH}"

# Copy source
COPY . .

# Startup commands and health checks belong to the owning Docker Compose
# deployment. The application entry point is scripts/validator.py::main.
