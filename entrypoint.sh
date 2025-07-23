# Apply database migrations
.venv/bin/python src/send_bills/manage.py migrate --noinput
# Start Gunicorn, binding to all interfaces on port 8000
.venv/bin/python -m gunicorn --bind "[::]:8000" send_bills.project.wsgi:application
