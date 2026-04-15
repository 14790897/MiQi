FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl git && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user to run the application (SEC-04)
RUN useradd -m -s /bin/bash -u 1000 miqi

WORKDIR /app

# Copy project metadata and lockfile first (cached layer)
COPY pyproject.toml uv.lock README.md LICENSE ./

# Copy the full source
COPY miqi/ miqi/

# Install with uv sync using the lockfile for reproducible builds
RUN uv sync --frozen --no-dev --no-editable

# Transfer ownership and create the config directory for the non-root user
RUN chown -R miqi:miqi /app && \
    mkdir -p /home/miqi/.miqi && \
    chown miqi:miqi /home/miqi/.miqi

# Switch to non-root user
USER miqi

# Add the project venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Gateway default port
EXPOSE 18790

ENTRYPOINT ["miqi"]
CMD ["status"]
