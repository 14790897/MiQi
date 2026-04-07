FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl git && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user to run the application (SEC-04)
RUN useradd -m -s /bin/bash -u 1000 miqi

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p miqi && touch miqi/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf miqi

# Copy the full source and install
COPY miqi/ miqi/
RUN uv pip install --system --no-cache .

# Transfer ownership and create the config directory for the non-root user
RUN chown -R miqi:miqi /app && \
    mkdir -p /home/miqi/.miqi && \
    chown miqi:miqi /home/miqi/.miqi

# Switch to non-root user
USER miqi

# Gateway default port
EXPOSE 18790

ENTRYPOINT ["miqi"]
CMD ["status"]
