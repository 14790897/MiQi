FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p featherflow && touch featherflow/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf featherflow

# Copy the full source and install
COPY featherflow/ featherflow/
RUN uv pip install --system --no-cache .

# Create config directory
RUN mkdir -p /root/.featherflow

# Gateway default port
EXPOSE 18790

ENTRYPOINT ["featherflow"]
CMD ["status"]
