# Apply database migrations
.venv/bin/python src/send_bills/manage.py migrate --noinput
# Start Gunicorn, binding to all interfaces on port 8000
.venv/bin/python -m gunicorn --no-control-socket --bind "[::]:8000" --timeout 300 send_bills.project.wsgi:application
