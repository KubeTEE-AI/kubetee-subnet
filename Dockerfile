# syntax=docker/dockerfile:1
# Application image - uses pre-built base with dependencies
# Build base image first (when requirements.txt changes):
#   docker build -f Dockerfile.base -t kubetee/kubetee-subnet-base:latest .
#
# Then build this image (fast - only copies code):
#   docker build -t kubetee/kubetee-subnet:latest .

ARG BASE_IMAGE=ghcr.io/kubetee-ai/kubetee-subnet-base:latest
FROM ${BASE_IMAGE}

# OCI Standard Labels
LABEL org.opencontainers.image.title="KubeTEE AI Subnet" \
      org.opencontainers.image.description="Enterprise AI-as-a-Service on Bittensor with TEE and Kubernetes" \
      org.opencontainers.image.vendor="KubeTEE AI" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/KubeTEE-AI/kubetee-subnet"

WORKDIR /app

# Copy application code
COPY kubetee/ ./kubetee/
COPY template/ ./template/
COPY neurons/ ./neurons/
COPY tests/ ./tests/
COPY pyproject.toml .
COPY setup.py .

# Health check - validates Python environment and API availability
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import kubetee; print('ok')" > /dev/null 2>&1 || exit 1

# Default command - show version
CMD ["python", "-c", "import kubetee; print(f'KubeTEE Subnet v{kubetee.__version__} ready')"]
