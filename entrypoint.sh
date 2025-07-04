#!/bin/sh

# Apply database migrations
echo "Applying database migrations..."
.venv/bin/python src/send_bills/manage.py migrate --noinput
echo "Migrations applied."

# Start Gunicorn, binding to all interfaces on port 8000
exec .venv/bin/python -m gunicorn --bind "[::]:8000" send_bills.project.wsgi:application
