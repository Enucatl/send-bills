# ---- Stage 1: The Builder ----
# Use a full-featured image to build our application artifacts
FROM python:3.13-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1

# Install system dependencies required for building Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2-dev \
    libffi-dev \
    libjpeg-dev \
    libxml2-dev \
    pkg-config \
    libpq-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project definition and install dependencies into the venv
# This is cached better than copying the whole app first
COPY MANIFEST.in pyproject.toml uv.lock ./
ARG VERSION=latest
ENV VERSION=${VERSION}
# Modify the pyproject.toml to set the version
RUN sed -i 's/enabled = true/enabled = false' pyproject.toml || true \
    && sed -i "s/dynamic = \\[\"version\"\\]/version = \"${VERSION}\"/" pyproject.toml
RUN uv sync --no-install-project --no-editable

# Copy the application source code and install it
COPY src/ src/
RUN uv sync --no-editable

# Create the static files directory before collecting
# /vol/web is a common pattern for persistent volumes, so we keep it
RUN mkdir -p /vol/web/staticfiles

# Collect static files using the python from our venv
RUN DJANGO_STATIC_ROOT=/vol/web/staticfiles DJANGO_SETTINGS_MODULE=send_bills.project.settings.development .venv/bin/python src/send_bills/manage.py collectstatic --noinput --clear

# Copy the entrypoint script for the final stage
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh


# ---- Stage 2: The Final Image ----
FROM python:3.13-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    tini \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for runtime
ENV PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=send_bills.project.settings.production \
    DJANGO_STATIC_ROOT=/vol/web/staticfiles

WORKDIR /app

# Copy artifacts from the builder stage
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /vol/web/staticfiles /vol/web/staticfiles
COPY --from=builder /app/entrypoint.sh /app/entrypoint.sh

# Expose the port Gunicorn will listen on
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD [".venv/bin/python", "-c", "import socket; s = socket.socket(); s.connect(('localhost', 8000))"]

ENTRYPOINT ["tini", "--", "/app/entrypoint.sh"]
