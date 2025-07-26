import datetime
import logging
from decimal import Decimal

import pandas as pd
import pytest

from django.db import IntegrityError
from rest_framework.response import Response
from django.urls import reverse
from django.utils import timezone

from send_bills.bills.models import (
    Bill,
    RecurringBill,
    get_date_offset_instance,
)
from send_bills.api.views import GenerateRecurringBillsAPIView


# --- Fixtures for common setup ---


@pytest.fixture
def generate_recurring_bills_url():
    """Provides the URL for the GenerateRecurringBillsAPIView."""
    return reverse("api:generate_recurring_bills")


@pytest.fixture
def generate_recurring_bills_view():
    """Provides the GenerateRecurringBillsAPIView as_view."""
    return GenerateRecurringBillsAPIView.as_view()


# --- Test Functions ---


@pytest.mark.django_db
def test_no_active_recurring_bills_found(
    request_factory,
    generate_recurring_bills_url,
    generate_recurring_bills_view,
    mocker,
    caplog,
    tzinfo,
):
    """Test response when no recurring bills exist."""
    mock_now = mocker.patch("send_bills.api.views.now")
    mock_now.return_value = timezone.datetime(2025, 1, 1, 10, 0, 0, tzinfo=tzinfo)

    caplog.set_level(logging.INFO, logger="send_bills.api.views")

    request = request_factory.post(generate_recurring_bills_url)
    response = generate_recurring_bills_view(request)

    assert response.status_code == 200
    assert isinstance(response, Response)
    assert response.data == {
        "status": "success",
        "message": "No active recurring bills found to process.",
        "generated_count": 0,
    }
    assert "No active recurring bills found to process." in caplog.text
    assert Bill.objects.count() == 0


@pytest.mark.django_db
def test_no_recurring_bills_due(
    request_factory,
    generate_recurring_bills_url,
    generate_recurring_bills_view,
    mocker,
    caplog,
    creditor_fixture,
    contact_fixture,
    tzinfo,
):
    """Test response when active recurring bills exist but none are due."""
    current_time = timezone.datetime(2025, 7, 15, 12, 0, 0, tzinfo=tzinfo)
    mocker.patch("send_bills.api.views.now", return_value=current_time)

    # Create a recurring bill whose next_billing_date is in the future
    future_date = current_time + datetime.timedelta(days=10)
    recurring_bill = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="100.00",
        description_template="Future Bill {{ billing_date.month }}",
        frequency="MonthEnd",
        start_date=current_time,
        next_billing_date=future_date,
        is_active=True,
    )

    caplog.set_level(logging.INFO, logger="send_bills.api.views")

    request = request_factory.post(generate_recurring_bills_url)
    response = generate_recurring_bills_view(request)

    assert response.status_code == 200
    assert isinstance(response, Response)
    assert "No active recurring" in response.data["message"]
    assert "No active recurring" in caplog.text
    assert Bill.objects.count() == 0

    # Ensure the recurring bill's next_billing_date was not altered
    recurring_bill.refresh_from_db()
    assert recurring_bill.next_billing_date == future_date


@pytest.mark.django_db
def test_successful_bill_generation_single(
    request_factory,
    generate_recurring_bills_url,
    generate_recurring_bills_view,
    mocker,
    caplog,
    creditor_fixture,
    contact_fixture,
    tzinfo,
):
    """Test successful generation of a single bill from a recurring schedule."""
    current_time = timezone.datetime(2025, 7, 20, 10, 0, 0, tzinfo=tzinfo)
    mocker.patch("send_bills.api.views.now", return_value=current_time)

    # Recurring bill is due (next_billing_date is in the past)
    due_date = current_time - datetime.timedelta(days=5)
    recurring_bill = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="150.00",
        description_template="Subscription for {{ billing_date.year }}-{{ billing_date.month }}",
        frequency="MonthBegin",
        frequency_kwargs={},
        start_date=due_date,
        next_billing_date=due_date,
        is_active=True,
    )

    caplog.set_level(logging.INFO, logger="send_bills.api.views")

    request = request_factory.post(generate_recurring_bills_url)
    response = generate_recurring_bills_view(request)

    assert response.status_code == 200
    assert response.data["status"] == "success"
    assert response.data["generated_count"] == 1
    assert "Successfully generated 1 bills" in response.data["message"]

    assert Bill.objects.count() == 1
    new_bill = Bill.objects.first()
    assert new_bill.contact == contact_fixture
    assert new_bill.creditor == creditor_fixture
    assert new_bill.amount == Decimal("150.00")
    assert new_bill.status == Bill.BillStatus.PENDING
    assert new_bill.recurring_bill == recurring_bill
    assert new_bill.billing_date == due_date
    assert new_bill.additional_information == "Subscription for 2025-7"
    assert new_bill.reference_number is not None

    recurring_bill.refresh_from_db()
    expected_next_billing_date = pd.Timestamp(due_date) + get_date_offset_instance(
        "MonthBegin"
    )
    assert recurring_bill.next_billing_date == expected_next_billing_date
    assert "Generated new bill" in caplog.text
    assert (
        f"Next billing date set to {expected_next_billing_date.isoformat()}"
        in caplog.text
    )


@pytest.mark.django_db
def test_successful_bill_generation_multiple_mixed(
    request_factory,
    generate_recurring_bills_url,
    generate_recurring_bills_view,
    mocker,
    caplog,
    creditor_fixture,
    contact_fixture,
    tzinfo,
):
    """Test processing of multiple recurring bills, some due, some not."""
    current_time = timezone.datetime(2025, 7, 20, 10, 0, 0, tzinfo=tzinfo)
    mocker.patch("send_bills.api.views.now", return_value=current_time)

    rb1_due_date = current_time - datetime.timedelta(days=10)
    rb1 = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="20.00",
        description_template="Due Bill 1",
        frequency="Week",
        start_date=rb1_due_date,
        next_billing_date=rb1_due_date,
        is_active=True,
    )

    rb2_future_date = current_time + datetime.timedelta(days=5)
    rb2 = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="30.00",
        description_template="Future Bill 2",
        frequency="MonthEnd",
        start_date=current_time,
        next_billing_date=rb2_future_date,
        is_active=True,
    )

    rb3_due_date = current_time
    rb3 = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="40.00",
        description_template="Due Bill 3",
        frequency="MonthBegin",
        start_date=rb3_due_date,
        next_billing_date=rb3_due_date,
        is_active=True,
    )

    rb4_inactive_date = current_time - datetime.timedelta(days=20)
    rb4 = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="50.00",
        description_template="Inactive Bill 4",
        frequency="Week",
        start_date=rb4_inactive_date,
        next_billing_date=rb4_inactive_date,
        is_active=False,
    )

    caplog.set_level(logging.INFO, logger="send_bills.api.views")

    request = request_factory.post(generate_recurring_bills_url)
    response = generate_recurring_bills_view(request)

    assert response.status_code == 200
    assert response.data["status"] == "success"
    assert response.data["generated_count"] == 2
    assert "Successfully generated 2 bills" in response.data["message"]

    assert Bill.objects.count() == 2
    generated_bills = Bill.objects.all().order_by("amount")
    assert generated_bills[0].amount == Decimal("20.00")
    assert generated_bills[1].amount == Decimal("40.00")

    rb1.refresh_from_db()
    expected_rb1_next_date = pd.Timestamp(rb1_due_date) + get_date_offset_instance(
        "Week"
    )
    assert rb1.next_billing_date == expected_rb1_next_date
    assert Bill.objects.filter(recurring_bill=rb1, billing_date=rb1_due_date).exists()

    rb2.refresh_from_db()
    assert rb2.next_billing_date == rb2_future_date
    assert not Bill.objects.filter(recurring_bill=rb2).exists()

    rb3.refresh_from_db()
    expected_rb3_next_date = pd.Timestamp(rb3_due_date) + get_date_offset_instance(
        "MonthBegin"
    )
    assert rb3.next_billing_date == expected_rb3_next_date
    assert Bill.objects.filter(recurring_bill=rb3, billing_date=rb3_due_date).exists()

    rb4.refresh_from_db()
    assert rb4.next_billing_date == rb4_inactive_date
    assert not Bill.objects.filter(recurring_bill=rb4).exists()
    assert "Generated new bill" in caplog.text
    assert "Successfully generated 2 bills" in response.data["message"]


@pytest.mark.django_db
def test_error_during_bill_generation_or_update(
    request_factory,
    generate_recurring_bills_url,
    generate_recurring_bills_view,
    mocker,
    caplog,
    creditor_fixture,
    contact_fixture,
    tzinfo,
):
    """Test error handling during the generation process."""
    current_time = timezone.datetime(2025, 8, 1, 10, 0, 0, tzinfo=tzinfo)
    mocker.patch("send_bills.api.views.now", return_value=current_time)

    rb_success_date = current_time - datetime.timedelta(days=1)
    rb_success = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="10.00",
        description_template="Successful Bill",
        frequency="MonthBegin",
        start_date=rb_success_date,
        next_billing_date=rb_success_date,
        is_active=True,
    )

    rb_fail_date = current_time - datetime.timedelta(days=2)
    rb_fail = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="20.00",
        description_template="Failing Bill",
        frequency="MonthBegin",
        start_date=rb_fail_date,
        next_billing_date=rb_fail_date,
        is_active=True,
    )

    original_bill_save = Bill.save

    def simulated_db_error_save(obj, *args, **kwargs):
        if obj.amount == Decimal("20.00"):
            raise IntegrityError("Simulated database error during Bill save")
        return original_bill_save(obj, *args, **kwargs)

    mocker.patch("send_bills.bills.models.Bill.save", new=simulated_db_error_save)

    caplog.set_level(logging.ERROR, logger="send_bills.api.views")

    request = request_factory.post(generate_recurring_bills_url)
    response = generate_recurring_bills_view(request)

    assert response.status_code == 200
    assert response.data["status"] == "partial_success"
    assert response.data["generated_count"] == 1
    assert len(response.data["errors"]) == 1
    assert f"RecurringBill {rb_fail.id}" in response.data["errors"][0]
    assert "Simulated database error" in response.data["errors"][0]

    assert Bill.objects.count() == 1
    assert Bill.objects.filter(recurring_bill=rb_success).exists()
    assert not Bill.objects.filter(recurring_bill=rb_fail).exists()

    rb_success.refresh_from_db()
    expected_rb_success_next_date = pd.Timestamp(
        rb_success_date
    ) + get_date_offset_instance("MonthBegin")
    assert rb_success.next_billing_date == expected_rb_success_next_date

    rb_fail.refresh_from_db()
    assert rb_fail.next_billing_date == rb_fail_date

    assert f"Unexpected error processing RecurringBill {rb_fail.id}" in caplog.text
    assert "Simulated database error during Bill save" in caplog.text


@pytest.mark.django_db
def test_next_billing_date_exactly_now(
    request_factory,
    generate_recurring_bills_url,
    generate_recurring_bills_view,
    mocker,
    creditor_fixture,
    contact_fixture,
    tzinfo,
):
    """Ensure bills are generated when next_billing_date is exactly the current time."""
    current_time = timezone.datetime(2025, 9, 1, 10, 30, 0, tzinfo=tzinfo)
    mocker.patch("send_bills.api.views.now", return_value=current_time)

    rb = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="75.00",
        description_template="Exact Time Bill",
        frequency="MonthBegin",
        start_date=current_time,
        next_billing_date=current_time,
        is_active=True,
    )

    request = request_factory.post(generate_recurring_bills_url)
    response = generate_recurring_bills_view(request)

    assert response.status_code == 200
    assert response.data["status"] == "success"
    assert response.data["generated_count"] == 1

    assert Bill.objects.count() == 1
    new_bill = Bill.objects.first()
    assert new_bill.amount == Decimal("75.00")
    assert new_bill.billing_date == current_time

    rb.refresh_from_db()
    expected_next_date = pd.Timestamp(current_time) + get_date_offset_instance(
        "MonthBegin"
    )
    assert rb.next_billing_date == expected_next_date
