FROM python:3.13-slim-bookworm

# Set environment variables for Python and Django settings
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE send_bills.project.settings.production
# Django will collect static files here, which Gunicorn will serve
ENV DJANGO_STATIC_ROOT /vol/web/staticfiles

# Install system dependencies required for Python packages (psycopg2-binary, cairosvg)
# and for running Django (e.g., build tools).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2-dev \
    libffi-dev \
    libjpeg-dev \
    libxml2-dev \
    pkg-config \
    postgresql-client \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system appuser
RUN pip install uv

# Create application directories and set ownership
# /app will be our WORKDIR, /vol/web/staticfiles is for Django static files
RUN mkdir -p /app /vol/web/staticfiles \
    && chown -R appuser:appuser /app /vol/web/staticfiles

# Copy the entrypoint script
COPY --chown=appuser:appuser entrypoint.sh /app
RUN chmod +x /app/entrypoint.sh

USER appuser
ENV HOME=/app

# Set working directory inside the container
WORKDIR /app

# Copy the requirements file and install Python dependencies
COPY --chown=appuser:appuser pyproject.toml .
ARG VERSION=latest
ENV VERSION=${VERSION}
# 1. Remove the [tool.setuptools-git-versioning] section
# 2. Change dynamic = ["version"] to version = "..."
RUN sed -i '/^\[tools\.setuptools-git-versioning\]/,/^\[/d' pyproject.toml || true \
    && sed -i '/^\[tools\.setuptools-git-versioning\]/d' pyproject.toml || true \
    && sed -i "s/dynamic = \\[\"version\"\\]/version = \"${VERSION}\"/" pyproject.toml
RUN uv sync --all-groups

# Install the full app
COPY --chown=appuser:appuser src/send_bills /app/src/send_bills
RUN uv pip install .

# Collect static files. Gunicorn will serve these in this setup.
RUN DJANGO_SETTINGS_MODULE=send_bills.project.settings.development .venv/bin/python src/send_bills/manage.py collectstatic --noinput --clear

# Expose the port Gunicorn will listen on
EXPOSE 8000

# Use the custom entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
