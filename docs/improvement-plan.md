# Send Bills Review And Improvement Plan

## Summary
- Replace the four public lifecycle API endpoints with one Django management command run by a compose scheduler service.
- Move production from an external Postgres URL to an in-stack Postgres container with a short downtime dump/restore cutover.
- Fix review findings that directly affect correctness, security, and operations: unauthenticated mutation endpoints, duplicate lifecycle races, repeat overdue emails, email/env config mismatches, and fragile Python dependency resolution.

## Review Findings Driving The Plan
- Security: DRF is configured with `AllowAny` and no auth classes in `src/send_bills/project/settings/base.py:47`, so all four billing mutation endpoints can be triggered publicly if routed.
- Lifecycle correctness: `GenerateRecurringBillsAPIView` and `SendPendingBillsAPIView` do not lock rows in `src/send_bills/api/views.py:134` and `src/send_bills/api/views.py:41`; concurrent calls can generate or send duplicates.
- Email side effects: email is sent inside database transactions in `src/send_bills/api/views.py:58` and `src/send_bills/api/views.py:273`; a later DB failure cannot unsend email and may cause retries/duplicates.
- Overdue reminders: `NotifyOverdueBillsAPIView` sends every overdue bill every time in `src/send_bills/api/views.py:254`, with no `last_notified_at` or interval tracking.
- Recipient bug: overdue email currently goes to the creditor, not the contact, in `src/send_bills/bills/utils.py:95`.
- Deployment config: compose exports `DJANGO_EMAIL_HOST_PORT` in `docker-compose.yml:17`, but settings read `DJANGO_EMAIL_PORT` in `src/send_bills/project/settings/base.py:109`.
- Config parsing: `EMAIL_USE_TLS = bool(os.environ.get(...))` in `src/send_bills/project/settings/base.py:112` makes `"False"` truthy.
- Packaging: `requires-python = ">= 3.13"` in `pyproject.toml:11` lets `uv` pick Python 3.14 locally, but `psycopg2-binary==2.9.10` lacks a compatible wheel and failed to build without `pg_config`.
- Data integrity: `Bill.reference_number` help text says unique, but migration `0007` removed the DB unique constraint; either make it unique again or update the invariant explicitly.

## Key Changes
- Add a `process_bills` management command that performs the lifecycle in a fixed order: generate due recurring bills, send pending bills, mark overdue sent bills, then send overdue reminders only when due.
- Move lifecycle logic out of API view classes into reusable service functions using `transaction.atomic()`, `select_for_update(skip_locked=True)` on Postgres-backed querysets, explicit ordering, and per-row result objects for logging/tests.
- Add `Bill.overdue_notified_at` and `Bill.overdue_notification_count`; notify only overdue unpaid bills where `overdue_notified_at` is null or older than 7 days, then update the fields after a successful send.
- Change overdue reminder recipient to `bill.contact.email`, keeping creditor as `cc`, matching normal bill sending behavior.
- Remove the four lifecycle URLs or leave them admin-only/internal with `IsAdminUser`; the scheduler must use the management command, not HTTP.
- Add a `scheduler` service to compose using the same app image and environment, running a simple cron/supercronic loop for `python src/send_bills/manage.py process_bills`.
- Add an in-stack `db` Postgres service with a named volume, healthcheck, internal network attachment, and `DATABASE_URL=postgres://...@db:5432/...` for `bills` and `scheduler`.
- Add `depends_on: db: condition: service_healthy` for app services, keep `migrate --noinput` in startup, and document backup/restore commands.
- Pin Python to `<3.14` or set `.python-version`/uv config to `3.13`; optionally replace `psycopg2-binary` with modern `psycopg[binary]`.
- Fix env parsing and names: use `DJANGO_EMAIL_PORT`, parse booleans with Django/env helper logic, and fail clearly when production `DATABASE_URL` is missing.

## Database Migration Plan
- Pre-cutover: deploy compose with `db` service stopped from serving app traffic, create named volume, and confirm target Postgres version.
- Backup: stop the current `bills` service, run `pg_dump --format=custom --no-owner --no-acl` from the external DB, and store the dump outside the container volume.
- Restore: start only the new `db`, run `pg_restore --clean --if-exists --no-owner --dbname "$NEW_DATABASE_URL" dumpfile`.
- Cutover: update production env to point `DATABASE_URL` at `db`, start `bills`, run migrations, create scheduler, then verify admin loads and row counts for contacts, creditors, recurring bills, and bills match source.
- Rollback: keep the external DB untouched until verification passes; rollback is switching `DATABASE_URL` back and stopping the in-stack `db`/scheduler.

## Test Plan
- Add unit tests for service functions covering no work, success, partial email failure, and concurrent-ish locked row behavior where supported.
- Add tests that repeated `process_bills` runs do not generate duplicate bills, resend pending bills, or resend overdue reminders before the 7-day interval.
- Add tests for overdue reminder recipient: contact in `to`, creditor in `cc`.
- Add config tests for `DJANGO_EMAIL_PORT`, boolean parsing, and production failure when `DATABASE_URL` is absent.
- Run `uv run ruff format .`, `uv run ruff check .`, and `DATABASE_URL="sqlite:///:memory:" uv run pytest src/send_bills/tests`.
- Also run at least one Postgres-backed test/check through compose because row locking and the new deployment target are Postgres-specific.

## Assumptions
- Use the recommended simple management-command scheduler, not Celery.
- Use a short downtime migration from the external production Postgres database.
- Overdue reminders should go to contacts, with creditors copied.
- Weekly overdue reminder cadence is acceptable unless a different interval is later configured.
- Existing production data must be preserved.
