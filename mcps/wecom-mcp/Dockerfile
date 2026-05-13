# ── Build stage ────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir build

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Build wheel
RUN python -m build --wheel --outdir /dist

# ── Runtime stage ────────────────────────────────────────────────
FROM python:3.11-slim

LABEL org.opencontainers.image.title="wecom-mcp"
LABEL org.opencontainers.image.description="WeCom (企业微信) MCP Server for AI Agents"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install runtime dependencies
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Copy env template
COPY .env.example .env.example

# Run as non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

# Default: start MCP Server (stdio mode)
# To start the webhook instead: docker run ... wecom-mcp-webhook
ENTRYPOINT ["python", "-m"]
CMD ["wecom_mcp.server"]

# Available commands:
#   python -m wecom_mcp.server           → MCP Server (stdio)
#   python -m wecom_mcp.webhook.handler   → Not directly; use uvicorn instead
