from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest

from send_bills.bills.models import Bill, RecurringBill
from send_bills.bills.services import process_bills
from send_bills.bills.services import (
    generate_due_recurring_bills,
    mark_overdue_bills,
    send_due_overdue_notifications,
    send_pending_bills,
)


@pytest.mark.django_db
def test_generate_due_recurring_bills_creates_bill(
    creditor_fixture, contact_fixture, mocker
):
    current_time = datetime(2025, 7, 20, 10, 0, 0, tzinfo=dt_timezone.utc)
    recurring_bill = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="150.00",
        description_template="Subscription for {{ billing_date.year }}-{{ billing_date.month }}",
        frequency="MonthBegin",
        start_date=current_time - timedelta(days=5),
        next_billing_date=current_time - timedelta(days=5),
        is_active=True,
    )

    results = generate_due_recurring_bills(current_time)

    assert len(results) == 1
    assert results[0].status == "processed"
    assert results[0].object_id == recurring_bill.id
    assert results[0].related_object_id is not None
    assert Bill.objects.count() == 1
    new_bill = Bill.objects.get()
    assert new_bill.amount == Decimal("150.00")

    recurring_bill.refresh_from_db()
    assert recurring_bill.next_billing_date > current_time


@pytest.mark.django_db
def test_generate_due_recurring_bills_reports_error(
    creditor_fixture, contact_fixture, mocker
):
    current_time = datetime(2025, 8, 1, 10, 0, 0, tzinfo=dt_timezone.utc)
    recurring_ok = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="10.00",
        description_template="Successful Bill",
        frequency="MonthBegin",
        start_date=current_time - timedelta(days=1),
        next_billing_date=current_time - timedelta(days=1),
        is_active=True,
    )
    recurring_fail = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="20.00",
        description_template="Failing Bill",
        frequency="MonthBegin",
        start_date=current_time - timedelta(days=2),
        next_billing_date=current_time - timedelta(days=2),
        is_active=True,
    )

    original_save = Bill.save

    def failing_save(obj, *args, **kwargs):
        if isinstance(obj, Bill) and obj.amount == Decimal("20.00"):
            raise RuntimeError("Simulated database error")
        return original_save(obj, *args, **kwargs)

    mocker.patch("send_bills.bills.models.Bill.save", new=failing_save)

    results = generate_due_recurring_bills(current_time)

    assert sorted(result.status for result in results) == ["error", "processed"]
    assert {result.object_id for result in results} == {
        recurring_ok.id,
        recurring_fail.id,
    }
    assert Bill.objects.count() == 1
    assert Bill.objects.filter(recurring_bill=recurring_ok).exists()
    assert not Bill.objects.filter(recurring_bill=recurring_fail).exists()


@pytest.mark.django_db
def test_send_pending_bills_updates_sent_status(
    creditor_fixture, contact_fixture, mocker
):
    current_time = datetime(2025, 7, 20, 10, 0, 0, tzinfo=dt_timezone.utc)
    pending_one = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount="100.00",
        status=Bill.BillStatus.PENDING,
    )
    pending_two = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount="200.00",
        status=Bill.BillStatus.PENDING,
    )
    sent_bill = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount="50.00",
        status=Bill.BillStatus.SENT,
        sent_at=current_time,
    )

    mock_send_bill_email = mocker.patch(
        "send_bills.bills.services.send_bill_email", return_value=1
    )

    results = send_pending_bills(current_time)

    assert [result.status for result in results] == ["processed", "processed"]
    assert mock_send_bill_email.call_count == 2

    pending_one.refresh_from_db()
    pending_two.refresh_from_db()
    sent_bill.refresh_from_db()

    assert pending_one.status == Bill.BillStatus.SENT
    assert pending_two.status == Bill.BillStatus.SENT
    assert pending_one.sent_at == current_time
    assert pending_two.sent_at == current_time
    assert sent_bill.status == Bill.BillStatus.SENT


@pytest.mark.django_db
def test_send_pending_bills_reports_partial_failure(
    creditor_fixture, contact_fixture, mocker
):
    current_time = datetime(2025, 7, 20, 10, 0, 0, tzinfo=dt_timezone.utc)
    pending_one = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount="100.00",
        status=Bill.BillStatus.PENDING,
    )
    pending_two = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount="200.00",
        status=Bill.BillStatus.PENDING,
    )

    mock_send_bill_email = mocker.patch("send_bills.bills.services.send_bill_email")
    mock_send_bill_email.side_effect = [1, Exception("Simulated network error")]

    results = send_pending_bills(current_time)

    assert [result.status for result in results] == ["processed", "error"]
    assert Bill.objects.get(pk=pending_one.pk).status == Bill.BillStatus.SENT
    assert Bill.objects.get(pk=pending_two.pk).status == Bill.BillStatus.PENDING


@pytest.mark.django_db
def test_mark_overdue_and_overdue_notifications(
    creditor_fixture, contact_fixture, mocker
):
    current_time = datetime(2025, 8, 10, 10, 0, 0, tzinfo=dt_timezone.utc)
    due_bill = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount="100.00",
        due_date=current_time - timedelta(days=1),
        status=Bill.BillStatus.PENDING,
    )
    already_overdue = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount="200.00",
        due_date=current_time - timedelta(days=10),
        status=Bill.BillStatus.OVERDUE,
        overdue_notified_at=current_time - timedelta(days=8),
    )
    recent_notice = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount="300.00",
        due_date=current_time - timedelta(days=20),
        status=Bill.BillStatus.OVERDUE,
        overdue_notified_at=current_time - timedelta(days=1),
    )
    future_bill = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount="400.00",
        due_date=current_time + timedelta(days=1),
        status=Bill.BillStatus.PENDING,
    )

    mark_results = mark_overdue_bills(current_time)
    assert [result.status for result in mark_results] == ["processed"]
    due_bill.refresh_from_db()
    assert due_bill.status == Bill.BillStatus.OVERDUE
    future_bill.refresh_from_db()
    assert future_bill.status == Bill.BillStatus.PENDING

    mock_send_overdue_email = mocker.patch(
        "send_bills.bills.services.send_overdue_email", return_value=1
    )
    notify_results = send_due_overdue_notifications(current_time)

    assert [result.status for result in notify_results] == ["processed", "processed"]
    assert mock_send_overdue_email.call_count == 2
    already_overdue.refresh_from_db()
    recent_notice.refresh_from_db()
    due_bill.refresh_from_db()
    assert due_bill.overdue_notification_count == 1
    assert due_bill.overdue_notified_at == current_time
    assert already_overdue.overdue_notification_count == 1
    assert already_overdue.overdue_notified_at == current_time
    assert recent_notice.overdue_notification_count == 0


@pytest.mark.django_db
def test_process_bills_is_idempotent(creditor_fixture, contact_fixture, mocker):
    current_time = datetime(2025, 9, 1, 10, 0, 0, tzinfo=dt_timezone.utc)
    recurring_bill = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="75.00",
        description_template="Exact Time Bill",
        frequency="MonthBegin",
        start_date=current_time,
        next_billing_date=current_time,
        is_active=True,
    )
    pending_bill = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount="50.00",
        status=Bill.BillStatus.PENDING,
    )
    overdue_bill = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount="25.00",
        due_date=current_time - timedelta(days=10),
        status=Bill.BillStatus.OVERDUE,
    )

    mock_send_bill_email = mocker.patch(
        "send_bills.bills.services.send_bill_email", return_value=1
    )
    mock_send_overdue_email = mocker.patch(
        "send_bills.bills.services.send_overdue_email", return_value=1
    )

    first_run = process_bills(current_time)
    second_run = process_bills(current_time)

    assert len(first_run.generated_bills) == 1
    assert len(first_run.sent_pending_bills) == 2
    assert len(first_run.marked_overdue_bills) == 0
    assert len(first_run.sent_overdue_notifications) == 1

    assert len(second_run.generated_bills) == 0
    assert len(second_run.sent_pending_bills) == 0
    assert len(second_run.marked_overdue_bills) == 0
    assert len(second_run.sent_overdue_notifications) == 0

    assert mock_send_bill_email.call_count == 2
    assert mock_send_overdue_email.call_count == 1

    recurring_bill.refresh_from_db()
    pending_bill.refresh_from_db()
    overdue_bill.refresh_from_db()
    assert recurring_bill.next_billing_date > current_time
    assert pending_bill.status == Bill.BillStatus.SENT
    assert Bill.objects.filter(status=Bill.BillStatus.SENT).count() == 2
    assert overdue_bill.overdue_notification_count == 1
