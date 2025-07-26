import logging
from datetime import timedelta

import pytest

from django.urls import reverse
from django.utils import timezone

from rest_framework.response import Response

from send_bills.bills.models import Bill
from send_bills.api.views import SendPendingBillsAPIView


@pytest.fixture
def setup_bills_for_sending(creditor_fixture, contact_fixture):
    """
    Sets up a set of bills with various statuses for testing sending.
    Returns a dictionary of these bills.
    """
    bills = {}
    bills["pending_1"] = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount=100.50,
        currency="CHF",
        status=Bill.BillStatus.PENDING,
    )
    bills["pending_2"] = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount=200.75,
        currency="CHF",
        status=Bill.BillStatus.PENDING,
    )
    bills["sent"] = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount=50.00,
        currency="CHF",
        status=Bill.BillStatus.SENT,
        sent_at=timezone.now(),
    )
    return bills


@pytest.fixture
def send_pending_bills_url():
    """Provides the URL for the SendPendingBillsAPIView."""
    return reverse(
        "api:send_pending_bills"
    )  # Assuming you have this URL name in your urls.py


@pytest.fixture
def send_pending_bills_view():
    """Provides the SendPendingBillsAPIView as_view."""
    return SendPendingBillsAPIView.as_view()


# --- Test Functions ---


@pytest.mark.django_db
def test_no_pending_bills_found(
    request_factory, send_pending_bills_url, send_pending_bills_view, mocker, caplog
):
    """Tests SendPendingBillsAPIView when no pending bills exist."""
    # Ensure no pending bills exist for this test
    Bill.objects.filter(status=Bill.BillStatus.PENDING).delete()

    mock_send_bill_email = mocker.patch("send_bills.api.views.send_bill_email")

    # Set up caplog to capture messages from the specific logger
    caplog.set_level(logging.INFO, logger="send_bills.api.views")

    request = request_factory.post(send_pending_bills_url)
    response = send_pending_bills_view(request)

    assert response.status_code == 200
    assert isinstance(response, Response)
    assert response.data == {
        "status": "success",
        "message": "No pending bills found to send.",
        "processed_count": 0,
    }
    mock_send_bill_email.assert_not_called()

    # Verify log messages
    assert "No pending bills found to send." in caplog.text


@pytest.mark.django_db
def test_successful_sending_of_all_pending_bills(
    request_factory,
    send_pending_bills_url,
    send_pending_bills_view,
    mocker,
    setup_bills_for_sending,
    caplog,
):
    """Tests SendPendingBillsAPIView for successful sending of pending bills."""
    bill_pending_1 = setup_bills_for_sending["pending_1"]
    bill_pending_2 = setup_bills_for_sending["pending_2"]
    bill_sent = setup_bills_for_sending["sent"]

    mock_send_bill_email = mocker.patch(
        "send_bills.api.views.send_bill_email", return_value=1
    )

    caplog.set_level(logging.INFO, logger="send_bills.api.views")

    request = request_factory.post(send_pending_bills_url)
    response = send_pending_bills_view(request)

    assert response.status_code == 200
    assert isinstance(response, Response)
    assert response.data == {
        "status": "success",
        "message": "Successfully sent and updated 2 pending bills.",
        "processed_count": 2,
    }

    # Assert send_bill_email was called for each pending bill
    assert mock_send_bill_email.call_count == 2
    # Verify exact calls, allowing for any order. Use mocker.call for comparison objects.
    assert mocker.call(bill_pending_1) in mock_send_bill_email.call_args_list
    assert mocker.call(bill_pending_2) in mock_send_bill_email.call_args_list

    # Assert bill statuses are updated
    bill_pending_1.refresh_from_db()
    assert bill_pending_1.status == Bill.BillStatus.SENT
    assert bill_pending_1.sent_at is not None
    assert (timezone.now() - bill_pending_1.sent_at) < timedelta(
        seconds=5
    )  # Check it's recent

    bill_pending_2.refresh_from_db()
    assert bill_pending_2.status == Bill.BillStatus.SENT
    assert bill_pending_2.sent_at is not None
    assert (timezone.now() - bill_pending_2.sent_at) < timedelta(seconds=5)

    bill_sent.refresh_from_db()  # Ensure non-pending bills are not touched
    assert bill_sent.status == Bill.BillStatus.SENT

    # Verify log messages
    assert "status updated to SENT" in caplog.text
    assert "Successfully sent and updated 2 pending bills." in response.data["message"]


@pytest.mark.django_db
def test_partial_success_with_some_failures(
    request_factory,
    send_pending_bills_url,
    send_pending_bills_view,
    mocker,
    setup_bills_for_sending,
    caplog,
):
    """Tests SendPendingBillsAPIView for partial success with some email sending failures."""
    bill_pending_1 = setup_bills_for_sending["pending_1"]
    bill_pending_2 = setup_bills_for_sending["pending_2"]

    # Configure mock_send_bill_email to succeed for one, fail for the other
    # The order of execution might not be guaranteed for QuerySet iteration,
    # so the side_effect should reflect this. Assuming `bill_pending_1` is processed first
    # based on typical ID ordering for default QuerySets, but the error message check
    # will be robust.
    mock_send_bill_email = mocker.patch("send_bills.api.views.send_bill_email")
    mock_send_bill_email.side_effect = [1, 0]  # 1 for first bill, 0 for second

    caplog.set_level(logging.INFO, logger="send_bills.api.views")

    request = request_factory.post(send_pending_bills_url)
    response = send_pending_bills_view(request)

    assert response.status_code == 200
    assert isinstance(response, Response)
    assert response.data["status"] == "partial_success"
    assert response.data["processed_count"] == 1
    assert len(response.data["errors"]) == 1

    # Find which bill corresponds to the error, as order is not strictly guaranteed
    failed_bill_id = None
    if mock_send_bill_email.call_args_list[0] == mocker.call(bill_pending_1):
        # If bill_pending_1 was first and succeeded, then bill_pending_2 failed
        failed_bill_id = bill_pending_2.id
    else:
        # If bill_pending_2 was first and succeeded, then bill_pending_1 failed
        failed_bill_id = bill_pending_1.id

    assert f"Bill {failed_bill_id}" in response.data["errors"][0]

    # Assert bill statuses
    bill_pending_1.refresh_from_db()
    bill_pending_2.refresh_from_db()

    # One of them is SENT, the other PENDING. We don't know which one based on this mock setup.
    assert (
        bill_pending_1.status == Bill.BillStatus.SENT
        and bill_pending_2.status == Bill.BillStatus.PENDING
    ) or (
        bill_pending_1.status == Bill.BillStatus.PENDING
        and bill_pending_2.status == Bill.BillStatus.SENT
    )

    if bill_pending_1.status == Bill.BillStatus.SENT:
        assert bill_pending_1.sent_at is not None
        assert bill_pending_2.sent_at is None
    else:
        assert bill_pending_1.sent_at is None
        assert bill_pending_2.sent_at is not None

    assert "Failed to send email for Bill" in response.data["errors"][0]


@pytest.mark.django_db
def test_unexpected_exception_during_processing(
    request_factory,
    send_pending_bills_url,
    send_pending_bills_view,
    mocker,
    setup_bills_for_sending,
    caplog,
):
    """Tests SendPendingBillsAPIView when an unexpected exception occurs during processing."""
    bill_pending_1 = setup_bills_for_sending["pending_1"]
    bill_pending_2 = setup_bills_for_sending["pending_2"]

    # Make the first call succeed, the second call raise an exception
    mock_send_bill_email = mocker.patch("send_bills.api.views.send_bill_email")
    mock_send_bill_email.side_effect = [1, Exception("Simulated network error")]

    caplog.set_level(logging.ERROR, logger="send_bills.api.views")

    request = request_factory.post(send_pending_bills_url)
    response = send_pending_bills_view(request)

    assert response.status_code == 200
    assert response.data["status"] == "partial_success"
    assert response.data["processed_count"] == 1
    assert len(response.data["errors"]) == 1

    # Similar logic for identifying the failed bill
    failed_bill_id = None
    if mock_send_bill_email.call_args_list[0] == mocker.call(bill_pending_1):
        failed_bill_id = bill_pending_2.id
    else:
        failed_bill_id = bill_pending_1.id

    assert f"Bill {failed_bill_id}" in response.data["errors"][0]
    assert "Unexpected error - Simulated network error" in response.data["errors"][0]

    # Assert bill statuses
    bill_pending_1.refresh_from_db()
    bill_pending_2.refresh_from_db()

    assert (
        bill_pending_1.status == Bill.BillStatus.SENT
        and bill_pending_2.status == Bill.BillStatus.PENDING
    ) or (
        bill_pending_1.status == Bill.BillStatus.PENDING
        and bill_pending_2.status == Bill.BillStatus.SENT
    )

    if bill_pending_1.status == Bill.BillStatus.SENT:
        assert bill_pending_1.sent_at is not None
        assert bill_pending_2.sent_at is None
    else:
        assert bill_pending_1.sent_at is None
        assert bill_pending_2.sent_at is not None

    assert "Unexpected error processing bill" in caplog.text
    assert "Simulated network error" in caplog.text
