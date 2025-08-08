from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from django.urls import reverse

from rest_framework import status

from send_bills.api.views import NotifyOverdueBillsAPIView, MarkOverdueBillsAPIView
from send_bills.bills.models import Bill, Creditor, Contact
from send_bills.bills.utils import send_overdue_email


@pytest.fixture
def overdue_bill_fixture(db, creditor_fixture, contact_fixture):
    """Creates an overdue Bill instance."""
    return Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount=100.00,
        due_date=datetime.now(tz=timezone.utc) - timedelta(days=5),
        status=Bill.BillStatus.OVERDUE,
    )


@pytest.fixture
def pending_bill_fixture(db, creditor_fixture, contact_fixture):
    """Creates a pending Bill instance."""
    return Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount=50.00,
        due_date=datetime.now(tz=timezone.utc) + timedelta(days=5),
        status=Bill.BillStatus.PENDING,
    )


@pytest.fixture
def paid_bill_fixture(db, creditor_fixture, contact_fixture):
    """Creates a paid Bill instance."""
    return Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount=75.00,
        due_date=datetime.now(tz=timezone.utc) - timedelta(days=15),
        status=Bill.BillStatus.PAID,
    )


# --- Test send_overdue_email function ---


@pytest.mark.django_db
def test_send_overdue_email_success(mocker, overdue_bill_fixture):
    """Tests send_overdue_email function for successful email sending."""
    # Patch internal dependencies of send_overdue_email
    mock_render_to_string = mocker.patch("send_bills.bills.utils.render_to_string")
    mock_generate_pdf = mocker.patch("send_bills.bills.utils.generate_pdf")
    mock_generate_attachment = mocker.patch(
        "send_bills.bills.utils.generate_attachment"
    )
    mock_email_message = mocker.patch("send_bills.bills.utils.EmailMessage")

    # Configure mocks
    mock_render_to_string.side_effect = [
        "Subject: Overdue Bill",
        "Body of the overdue email",
    ]
    mock_generate_pdf.return_value = b"mock_pdf_content"
    mock_generate_attachment.return_value = (
        "bill.pdf",
        b"mock_pdf_content",
        "application/pdf",
    )

    # Mock the EmailMessage instance's send method
    mock_email_instance = mocker.MagicMock()
    mock_email_instance.send.return_value = 1  # Simulate successful sending
    mock_email_message.return_value = mock_email_instance

    # Call the function
    sent_count = send_overdue_email(overdue_bill_fixture)

    # Assertions
    assert sent_count == 1

    # Assert render_to_string was called correctly
    mock_render_to_string.assert_has_calls([
        mocker.call(
            "emails/overdue_subject.txt", context={"bill": overdue_bill_fixture}
        ),
        mocker.call("emails/overdue_body.txt", context={"bill": overdue_bill_fixture}),
    ])

    # Assert PDF and attachment generation
    mock_generate_pdf.assert_called_once_with(overdue_bill_fixture)
    mock_generate_attachment.assert_called_once_with(
        b"mock_pdf_content", filename="bill.pdf"
    )

    # Assert EmailMessage was instantiated correctly
    mock_email_message.assert_called_once_with(
        subject="Subject: Overdue Bill",
        body="Body of the overdue email",
        from_email=overdue_bill_fixture.creditor.email,
        to=[overdue_bill_fixture.creditor.email],
        attachments=[("bill.pdf", b"mock_pdf_content", "application/pdf")],
    )

    # Assert send method was called
    mock_email_instance.send.assert_called_once_with(fail_silently=False)


def test_send_overdue_email_failure(mocker, overdue_bill_fixture):
    """Tests send_overdue_email function for failed email sending."""
    # Patch internal dependencies of send_overdue_email
    mock_render_to_string = mocker.patch("send_bills.bills.utils.render_to_string")
    mock_generate_pdf = mocker.patch("send_bills.bills.utils.generate_pdf")
    mock_generate_attachment = mocker.patch(
        "send_bills.bills.utils.generate_attachment"
    )
    mock_email_message = mocker.patch("send_bills.bills.utils.EmailMessage")

    # Configure mocks for failure
    mock_render_to_string.side_effect = [
        "Subject: Overdue Bill",
        "Body of the overdue email",
    ]
    mock_generate_pdf.return_value = b"mock_pdf_content"
    mock_generate_attachment.return_value = (
        "bill.pdf",
        b"mock_pdf_content",
        "application/pdf",
    )

    # Simulate EmailMessage.send() returning 0 (failure)
    mock_email_instance = mocker.MagicMock()
    mock_email_instance.send.return_value = 0
    mock_email_message.return_value = mock_email_instance

    # Call the function
    sent_count = send_overdue_email(overdue_bill_fixture)

    # Assertions
    assert sent_count == 0
    mock_email_instance.send.assert_called_once_with(fail_silently=False)


# --- Test MarkOverdueBillsAPIView ---


@pytest.fixture
def mark_overdue_url():
    """Provides the URL for the MarkOverdueBillsAPIView."""
    return reverse("api:mark_overdue_bills")


@pytest.fixture
def mark_overdue_view():
    """Provides the MarkOverdueBillsAPIView as_view."""
    return MarkOverdueBillsAPIView.as_view()


@freeze_time("2023-10-26")  # Freeze time to control now() for these tests
@pytest.mark.django_db
def test_mark_overdue_bills_no_updates_needed(
    request_factory,
    mark_overdue_url,
    mark_overdue_view,
    creditor_fixture,
    contact_fixture,
    today_date,
):
    """Tests MarkOverdueBillsAPIView when no bills need to be updated."""
    # Bill due in future
    Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        due_date=today_date + timedelta(days=1),
        status=Bill.BillStatus.PENDING,
        amount=100,
    )
    # Bill already overdue
    Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        due_date=today_date - timedelta(days=30),
        status=Bill.BillStatus.OVERDUE,
        amount=200,
    )
    bill_paid_past_due = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        due_date=today_date - timedelta(days=15),
        status=Bill.BillStatus.PAID,
        amount=300,
    )

    response = mark_overdue_view(request_factory.post(mark_overdue_url))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "success"
    assert response.data["message"] == "Checked and updated overdue bills."
    assert response.data["updated_count"] == 0  # No bills should be updated

    # Verify database state
    assert (
        Bill.objects.get(due_date=today_date + timedelta(days=1)).status
        == Bill.BillStatus.PENDING
    )
    assert (
        Bill.objects.get(due_date=today_date - timedelta(days=30)).status
        == Bill.BillStatus.OVERDUE
    )
    assert Bill.objects.get(pk=bill_paid_past_due.pk).status == Bill.BillStatus.PAID


@freeze_time("2023-10-26")
@pytest.mark.django_db
def test_mark_overdue_bills_some_updated(
    request_factory,
    mark_overdue_url,
    mark_overdue_view,
    creditor_fixture,
    creditor2_fixture,
    contact_fixture,
    today_date,
):
    """Tests MarkOverdueBillsAPIView when some bills are updated to overdue."""
    # Bills that should be updated
    bill1 = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        due_date=today_date - timedelta(days=1),  # yesterday
        status=Bill.BillStatus.PENDING,
        amount=100,
    )
    bill2 = Bill.objects.create(
        creditor=creditor2_fixture,
        contact=contact_fixture,
        due_date=today_date - timedelta(days=30),  # long ago
        status=Bill.BillStatus.PENDING,
        amount=200,
    )
    # Bill that should NOT be updated (already overdue)
    bill3 = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        due_date=today_date - timedelta(days=30),
        status=Bill.BillStatus.OVERDUE,
        amount=300,
    )
    # Bill that should NOT be updated (due in future)
    bill4 = Bill.objects.create(
        creditor=creditor2_fixture,
        contact=contact_fixture,
        due_date=today_date + timedelta(days=1),  # tomorrow
        status=Bill.BillStatus.PENDING,
        amount=400,
    )
    # Bill due today and pending
    bill5 = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        due_date=today_date,  # today
        status=Bill.BillStatus.PENDING,
        amount=500,
    )
    bill_paid = Bill.objects.create(
        creditor=creditor2_fixture,
        contact=contact_fixture,
        due_date=today_date - timedelta(days=10),
        status=Bill.BillStatus.PAID,
        amount=600,
    )

    response = mark_overdue_view(request_factory.post(mark_overdue_url))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "success"
    assert response.data["message"] == "Checked and updated overdue bills."
    assert response.data["updated_count"] == 3  # bill1, bill2, bill5 should be updated

    # Verify database state
    assert Bill.objects.get(pk=bill1.pk).status == Bill.BillStatus.OVERDUE
    assert Bill.objects.get(pk=bill2.pk).status == Bill.BillStatus.OVERDUE
    assert Bill.objects.get(pk=bill3.pk).status == Bill.BillStatus.OVERDUE  # No change
    assert Bill.objects.get(pk=bill4.pk).status == Bill.BillStatus.PENDING  # No change
    assert Bill.objects.get(pk=bill5.pk).status == Bill.BillStatus.OVERDUE
    assert Bill.objects.get(pk=bill_paid.pk).status == Bill.BillStatus.PAID


# --- Test NotifyOverdueBillsAPIView ---


@pytest.fixture
def notify_overdue_url():
    """Provides the URL for the NotifyOverdueBillsAPIView."""
    return reverse("api:notify_overdue_bills")


@pytest.fixture
def notify_overdue_view():
    """Provides the NotifyOverdueBillsAPIView as_view."""
    return NotifyOverdueBillsAPIView.as_view()


# Re-create these specific bills for the notify tests to ensure they're distinct
# from other fixtures if multiple tests run in different orders/scopes.
@pytest.fixture
@pytest.mark.django_db
def notify_test_bills(
    creditor_fixture, creditor2_fixture, contact_fixture, contact2_fixture
):
    overdue_bill1 = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount=100,
        due_date=datetime.now(tz=timezone.utc) - timedelta(days=10),
        status=Bill.BillStatus.OVERDUE,
    )
    overdue_bill2 = Bill.objects.create(
        creditor=creditor2_fixture,
        contact=contact2_fixture,
        amount=200,
        due_date=datetime.now(tz=timezone.utc) - timedelta(days=5),
        status=Bill.BillStatus.OVERDUE,
    )
    pending_bill = Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount=50,
        due_date=datetime.now(tz=timezone.utc) + timedelta(days=5),
        status=Bill.BillStatus.PENDING,
    )
    paid_bill = Bill.objects.create(
        creditor=creditor2_fixture,
        contact=contact2_fixture,
        amount=75,
        due_date=datetime.now(tz=timezone.utc) - timedelta(days=15),
        status=Bill.BillStatus.PAID,
    )
    return {
        "overdue_bill1": overdue_bill1,
        "overdue_bill2": overdue_bill2,
        "pending_bill": pending_bill,
        "paid_bill": paid_bill,
    }


def test_notify_overdue_bills_success(
    mocker, request_factory, notify_overdue_url, notify_overdue_view, notify_test_bills
):
    """Tests NotifyOverdueBillsAPIView for successful notifications."""
    # Patch the send_overdue_email function where it is imported/used in NotifyOverdueBillsAPIView
    mock_send_overdue_email = mocker.patch("send_bills.api.views.send_overdue_email")
    mock_send_overdue_email.return_value = (
        1  # Simulate successful email sending for all overdue bills
    )

    response = notify_overdue_view(request_factory.post(notify_overdue_url))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "success"
    assert response.data["message"] == "Successfully sent 2 overdue bill notifications."
    assert response.data["errors"] == []
    assert (
        response.data["notifications"] == 2
    )  # Two bills were overdue and should have been processed

    # Ensure send_overdue_email was called for the correct bills
    assert mock_send_overdue_email.call_count == 2
    mock_send_overdue_email.assert_has_calls(
        [
            mocker.call(notify_test_bills["overdue_bill1"]),
            mocker.call(notify_test_bills["overdue_bill2"]),
        ],
        any_order=True,
    )


@pytest.mark.django_db
def test_notify_overdue_bills_no_overdue_bills(
    request_factory, notify_overdue_url, notify_overdue_view, mocker
):
    """Tests NotifyOverdueBillsAPIView when no overdue bills are found."""
    # Ensure there are no overdue bills
    Bill.objects.all().delete()
    # Add a non-overdue bill to ensure context is correct
    Bill.objects.create(
        creditor=Creditor.objects.create(name="Temp"),
        contact=Contact.objects.create(name="Temp"),
        amount=10,
        due_date=datetime.now(tz=timezone.utc) + timedelta(days=1),
        status=Bill.BillStatus.PENDING,
    )

    mock_send_overdue_email = mocker.patch("send_bills.api.views.send_overdue_email")

    response = notify_overdue_view(request_factory.post(notify_overdue_url))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "success"
    assert response.data["message"] == "No overdue bills found to notify."
    assert response.data["errors"] == []
    assert response.data["notifications"] == 0  # No notifications sent

    mock_send_overdue_email.assert_not_called()


def test_notify_overdue_bills_some_failures(
    mocker, request_factory, notify_overdue_url, notify_overdue_view, notify_test_bills
):
    """Tests NotifyOverdueBillsAPIView when some notifications fail."""
    # Simulate one success, one failure
    mock_send_overdue_email = mocker.patch("send_bills.api.views.send_overdue_email")
    mock_send_overdue_email.side_effect = [
        1,  # First call succeeds
        0,  # Second call fails
    ]

    response = notify_overdue_view(request_factory.post(notify_overdue_url))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "partial_success"
    assert "Sent 1 overdue notifications successfully." in response.data["message"]
    assert response.data["notifications"] == 1  # Only one succeeded

    # Check errors list (order may vary based on iterator)
    errors = response.data["errors"]
    assert len(errors) == 1
    # Check if the error message contains the expected bill (the one that failed)
    # Determine which bill will fail by checking the order send_overdue_email receives them
    # Since it's iterating over a QuerySet, the order isn't guaranteed,
    # so we'll check if either overdue bill's PK is in the error message.
    failed_bill_found = False
    for error_msg in errors:
        if (
            str(notify_test_bills["overdue_bill1"].pk) in error_msg
            or str(notify_test_bills["overdue_bill2"].pk) in error_msg
        ):
            failed_bill_found = True
            break
    assert failed_bill_found

    assert mock_send_overdue_email.call_count == 2  # Both were attempted
