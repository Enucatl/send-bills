# Django Bills Manager

[![GitHub Actions CI/CD](https://github.com/Enucatl/send-bills/actions/workflows/deploy.yml/badge.svg)](https://github.com/Enucatl/send-bills/actions/workflows/deploy.yml)
[![Made with Python](https://img.shields.io/badge/made%20with-Python-green.svg)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

A robust and automated Django application for managing, generating, and sending invoices, with first-class support for **Swiss QR-Bills** and automated payment reconciliation.

This project is designed to be run as a containerized service, controlled via a powerful Django admin interface and automated through a Django management command. It's perfect for small businesses, freelancers, or associations that need a streamlined invoicing workflow.


## ✨ Key Features

- **Full Bill Lifecycle Management**: Create, track, and manage bills from "Pending" to "Paid" through a clean Django admin interface.
- **Recurring Invoices**: Automatically generate bills on flexible schedules (e.g., monthly, quarterly, weekly) using powerful `pandas` DateOffsets.
- **Swiss QR-Bill Generation**: Automatically generates valid Swiss QR-Bill PDFs for every invoice, ensuring compliance and ease of payment for your clients.
- **Automated Emailing**:
    - Dispatches newly generated bills to contacts via email, with the PDF invoice attached.
    - Sends automated overdue reminders for unpaid bills.
- **Automated Payment Reconciliation**: Upload your bank's transaction CSV file to automatically match payments to open invoices and mark them as paid.
- **Automated Billing Command**: A single management command to trigger billing tasks, perfect for `cron` jobs or other scheduled task runners.
- **Containerized & Production-Ready**: Comes with `Dockerfile` and `docker-compose.yml` configurations for easy deployment.
- **Secure Authentication**: Designed to integrate seamlessly with reverse-proxy authentication systems like Authelia.
- **CI/CD Pipeline**: Includes a GitHub Actions workflow for automated testing, Docker image building, and deployment to GitHub Container Registry.

## 🛠️ Technology Stack

- **Backend**: Django, Django REST Framework
- **Database**: PostgreSQL (recommended), compatible with other Django DBs.
- **PDF Generation**: `qrbill` for QR-bill data, `cairosvg` for PDF rendering. **Data Handling**: `pandas` for CSV processing and date calculations.
- **Web Server**: Gunicorn with WhiteNoise for serving static files.
- **Containerization**: Docker & Docker Compose.
- **CI/CD**: GitHub Actions.

## 🚀 Getting Started

### Prerequisites

- [uv](https://github.com/astral-sh/uv) (for package management)
- Docker & Docker Compose (for running the application)

### 1. Local Development Setup

Follow these steps to get a local development server running.

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/enucatl/send-bills.git
    cd send-bills
    ```

2.  **Set Up Virtual Environment & Install Dependencies:**
    ```bash
    # Create a virtual environment
    python -m venv .venv
    source .venv/bin/activate

    # Install all dependencies using uv
    uv sync --all-extras
    ```

3.  **Configure Environment Variables:**
    The application uses `dj-database-url` to configure the database. Create a `.env` file in the root directory for your local environment variables.
    ```env
    # .env
    DATABASE_URL=postgres://user:password@localhost:5432/bills_db
    # DJANGO_SETTINGS_MODULE defaults to development, so it's not strictly needed here.
    ```
    For a simpler start, you can use SQLite:
    ```env
    # .env
    DATABASE_URL=sqlite:///db.sqlite3
    ```

4.  **Run Database Migrations:**
    ```bash
    python src/send_bills/manage.py migrate
    ```

5.  **Run the Development Server:**
    The local server uses a development middleware to simulate authentication. By default, you will be logged in as `devuser`.
    ```bash
    python src/send_bills/manage.py runserver
    ```
    You can now access the Django Admin at `http://127.0.0.1:8000/admin/`.

### 2. Running with Docker Compose

For a more production-like local environment, you can use Docker Compose.

1.  **Create a `.env` file** with your database configuration:
    ```env
    # .env
    DATABASE_URL=postgres://user:password@host.home.arpa:5432/bills_db
    ```

2.  **Build and Run the Container:**
    The `docker-compose.dev.yml` is configured for local development.
    ```bash
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
    ```
    The application will be available at `http://localhost:8000/`.

## ⚙️ Usage & Workflow

The primary interface for this application is the Django Admin. The core workflow is as follows:

1.  **Create Creditors and Contacts**:
    - Go to the `Creditors` section and add your company's details (Name, IBAN, etc.).
    - Go to the `Contacts` section and add your clients' details.

2.  **Create Bills**:
    - **One-off Bills**: Navigate to `Bills` and click "Add bill". Fill in the details. The status will default to `Pending`.
    - **Recurring Bills**: Navigate to `Recurring bills` and "Add recurring bill". Define a template, amount, and a `frequency` (e.g., `MonthEnd`, `QuarterBegin`).

3.  **Automate Billing Tasks**:
    Run the lifecycle with one command:
    ```bash
    python src/send_bills/manage.py process_bills
    ```

    A scheduler service can run this command on a fixed interval.

4.  **Reconcile Payments**:
    - In the `Creditors` admin list view, click the **"Upload CSV"** button.
    - Upload your bank transaction export (specifically formatted CSVs, see `src/send_bills/bills/tests/transactions.csv` for an example).
    - The system will parse the file, find payments matching the `SCOR` reference, and automatically mark the corresponding bills as `Paid`.

## 🧪 Testing

The project has a comprehensive test suite. To run the tests:

```bash
# Run the pytest suite with a temporary in-memory database
DATABASE_URL="sqlite:///:memory:" uv run pytest src/send_bills/tests
```

## 🚢 Deployment

This application is built to be deployed as a Docker container.

### Environment Variables

For production, you must configure the following environment variables:

- `DJANGO_SECRET_KEY`: A long, random string.
- `DJANGO_ALLOWED_HOSTS`: Comma-separated list of allowed hostnames (e.g., `bills.example.com`).
- `CSRF_TRUSTED_ORIGINS`: Comma-separated list of trusted origins (e.g., `https://bills.example.com`).
- `DATABASE_URL`: The full connection string for your PostgreSQL database.
- `DJANGO_EMAIL_HOST`: Your SMTP server hostname.
- `DJANGO_EMAIL_PORT`: Your SMTP server port.
- `DJANGO_EMAIL_HOST_USER`: Your SMTP username.
- `DJANGO_EMAIL_HOST_PASSWORD`: Your SMTP password.

### Database Cutover

When moving from the old external Postgres database to the new in-stack `db`
service, do a short downtime dump/restore:

1. Stop the application container so it stops writing to the old database.
2. Dump the old database from the current production connection:
   ```bash
   pg_dump --format=custom --no-owner --no-acl "$OLD_DATABASE_URL" > bills.dump
   ```
3. Start the new `db` service only.
4. Restore the dump into the new instance:
   ```bash
   pg_restore --clean --if-exists --no-owner --dbname "$NEW_DATABASE_URL" bills.dump
   ```
5. Point production `DATABASE_URL` at the new in-stack database and start the
   `bills` and `scheduler` services.
6. Verify admin access and row counts before deleting the dump.

### CI/CD Pipeline

The included GitHub Actions workflow (`.github/workflows/deploy.yml`) automates the following process on every push to `main`:

1.  **Build & Test**: Installs dependencies and


## Install
```
uv sync --all-extras
```

## Test
```
DATABASE_URL=$(vault kv get -field=uri kv/airflow/connections/djangodev) uv run pytest src/send_bills/tests
```

## Run development server
```
DATABASE_URL=$(vault kv get -field=uri kv/airflow/connections/djangodev) .venv/bin/python src/send_bills/manage.py runserver
```

## Run development docker
```
VERSION=$(uv run setuptools-git-versioning) docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## Run production docker
```
docker compose build --build-arg VERSION=$(uv run setuptools-git-versioning)
docker compose -f docker-compose.yml up -d
```

## Security baseline

This compose project uses the shared [docker-compose-security-baseline](https://github.com/Enucatl/docker-compose-security-baseline) for common container hardening defaults, including capabilities, no-new-privileges, memory/swap, and PID limits.
