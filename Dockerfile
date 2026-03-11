FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl git && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user to run the application (SEC-04)
RUN useradd -m -s /bin/bash -u 1000 featherflow

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p featherflow && touch featherflow/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf featherflow

# Copy the full source and install
COPY featherflow/ featherflow/
RUN uv pip install --system --no-cache .

# Transfer ownership and create the config directory for the non-root user
RUN chown -R featherflow:featherflow /app && \
    mkdir -p /home/featherflow/.featherflow && \
    chown featherflow:featherflow /home/featherflow/.featherflow

# Switch to non-root user
USER featherflow

# Gateway default port
EXPOSE 18790

ENTRYPOINT ["featherflow"]
CMD ["status"]
