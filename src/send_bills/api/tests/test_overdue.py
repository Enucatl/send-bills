from datetime import datetime, timedelta, timezone
from unittest import mock

from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase, APIRequestFactory

from freezegun import freeze_time

from send_bills.api.views import NotifyOverdueBillsAPIView, MarkOverdueBillsAPIView
from send_bills.bills.models import Bill, Creditor, Contact
from send_bills.bills.utils import send_overdue_email


# --- Test send_overdue_email function ---

# Patching path for send_overdue_email:
# If send_overdue_email is in your_app_name/views.py and called from there,
# its path would be 'your_app_name.views.send_overdue_email'.
# But if it's imported into views from another module (e.g., utils),
# say `from .utils import send_overdue_email`, then when testing the view,
# you'd patch it as `your_app_name.views.send_overdue_email`.
# For testing the function directly, you patch its internal dependencies.


class SendOverdueEmailTest(APITestCase):  # APITestCase provides DB setup and clean-up
    def setUp(self):
        self.creditor = Creditor.objects.create(
            name="Test Creditor AG",
            city="Zurich",
            pcode="8000",
            country="CH",
            iban="CH41002721071046C2492",
            email="creditor@example.com",
        )
        self.contact = Contact.objects.create(
            name="Contact A", email="contact_a@example.com"
        )
        self.bill = Bill.objects.create(
            creditor=self.creditor,
            contact=self.contact,
            amount=100.00,
            due_date=datetime.now(tz=timezone.utc) - timedelta(days=5),
            status=Bill.BillStatus.OVERDUE,
        )

    @mock.patch("send_bills.bills.utils.render_to_string")
    @mock.patch("send_bills.bills.utils.generate_pdf")
    @mock.patch("send_bills.bills.utils.generate_attachment")
    @mock.patch("send_bills.bills.utils.EmailMessage")
    def test_send_overdue_email_success(
        self,
        mock_email_message,
        mock_generate_attachment,
        mock_generate_pdf,
        mock_render_to_string,
    ):
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
        mock_email_instance = mock.MagicMock()
        mock_email_instance.send.return_value = 1  # Simulate successful sending
        mock_email_message.return_value = mock_email_instance

        # Call the function
        sent_count = send_overdue_email(self.bill)

        # Assertions
        self.assertEqual(sent_count, 1)

        # Assert render_to_string was called correctly
        mock_render_to_string.assert_has_calls([
            mock.call("emails/overdue_subject.txt", context={"bill": self.bill}),
            mock.call("emails/overdue_body.txt", context={"bill": self.bill}),
        ])

        # Assert PDF and attachment generation
        mock_generate_pdf.assert_called_once_with(self.bill)
        mock_generate_attachment.assert_called_once_with(b"mock_pdf_content")

        # Assert EmailMessage was instantiated correctly
        mock_email_message.assert_called_once_with(
            subject="Subject: Overdue Bill",
            body="Body of the overdue email",
            from_email=self.bill.creditor.email,
            to=[self.bill.creditor.email],
            attachments=[("bill.pdf", b"mock_pdf_content", "application/pdf")],
        )

        # Assert send method was called
        mock_email_instance.send.assert_called_once_with(fail_silently=False)

    @mock.patch("send_bills.bills.utils.render_to_string")
    @mock.patch("send_bills.bills.utils.generate_pdf")
    @mock.patch("send_bills.bills.utils.generate_attachment")
    @mock.patch("send_bills.bills.utils.EmailMessage")
    def test_send_overdue_email_failure(
        self,
        mock_email_message,
        mock_generate_attachment,
        mock_generate_pdf,
        mock_render_to_string,
    ):
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
        mock_email_instance = mock.MagicMock()
        mock_email_instance.send.return_value = 0
        mock_email_message.return_value = mock_email_instance

        # Call the function
        sent_count = send_overdue_email(self.bill)

        # Assertions
        self.assertEqual(sent_count, 0)
        mock_email_instance.send.assert_called_once_with(fail_silently=False)


# --- Test MarkOverdueBillsAPIView ---


class MarkOverdueBillsAPITest(APITestCase):
    def setUp(self):
        self.client = APIRequestFactory()
        self.url = reverse("api:mark_overdue_bills")
        self.view = MarkOverdueBillsAPIView.as_view()

        self.creditor1 = Creditor.objects.create(
            name="Test Creditor 1",
            city="Zurich",
            pcode="8000",
            country="CH",
            iban="CH41002721071046C2492",
            email="creditor1@example.com",
        )
        self.creditor2 = Creditor.objects.create(
            name="Test Creditor 2",
            city="Zurich",
            pcode="8000",
            country="CH",
            iban="CH801503791J674321901",
            email="creditor2@example.com",
        )
        self.contact = Contact.objects.create(
            name="Contact A", email="contact_a@example.com"
        )

        # Use fixed dates for predictability
        self.today = datetime(2023, 10, 26, tzinfo=timezone.utc)  # Arbitrary fixed date
        self.yesterday = self.today - timedelta(days=1)
        self.tomorrow = self.today + timedelta(days=1)
        self.long_ago = self.today - timedelta(days=30)

    @freeze_time("2023-10-26")  # Freeze time to control now()
    def test_mark_overdue_bills_no_updates_needed(self):
        # Bill due in future
        Bill.objects.create(
            creditor=self.creditor1,
            contact=self.contact,
            due_date=self.tomorrow,
            status=Bill.BillStatus.PENDING,
            amount=100,
        )
        # Bill already overdue
        Bill.objects.create(
            creditor=self.creditor1,
            contact=self.contact,
            due_date=self.long_ago,
            status=Bill.BillStatus.OVERDUE,
            amount=200,
        )

        response = self.view(self.client.post(self.url))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["message"], "checked overdue bills")
        self.assertEqual(
            response.data["updated_count"], 0
        )  # No bills should be updated

        # Verify database state
        self.assertEqual(
            Bill.objects.get(due_date=self.tomorrow).status, Bill.BillStatus.PENDING
        )
        self.assertEqual(
            Bill.objects.get(due_date=self.long_ago).status, Bill.BillStatus.OVERDUE
        )

    @freeze_time("2023-10-26")
    def test_mark_overdue_bills_some_updated(self):
        # Bills that should be updated
        bill1 = Bill.objects.create(
            creditor=self.creditor1,
            contact=self.contact,
            due_date=self.yesterday,
            status=Bill.BillStatus.PENDING,
            amount=100,
        )
        bill2 = Bill.objects.create(
            creditor=self.creditor2,
            contact=self.contact,
            due_date=self.long_ago,
            status=Bill.BillStatus.PENDING,
            amount=200,
        )
        # Bill that should NOT be updated (already overdue)
        bill3 = Bill.objects.create(
            creditor=self.creditor1,
            contact=self.contact,
            due_date=self.long_ago,
            status=Bill.BillStatus.OVERDUE,
            amount=300,
        )
        # Bill that should NOT be updated (due in future)
        bill4 = Bill.objects.create(
            creditor=self.creditor2,
            contact=self.contact,
            due_date=self.tomorrow,
            status=Bill.BillStatus.PENDING,
            amount=400,
        )
        # Bill due today and pending
        bill5 = Bill.objects.create(
            creditor=self.creditor1,
            contact=self.contact,
            due_date=self.today,
            status=Bill.BillStatus.PENDING,
            amount=500,
        )

        response = self.view(self.client.post(self.url))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["message"], "checked overdue bills")
        self.assertEqual(
            response.data["updated_count"], 3
        )  # bill1, bill2, bill5 should be updated

        # Verify database state
        self.assertEqual(Bill.objects.get(pk=bill1.pk).status, Bill.BillStatus.OVERDUE)
        self.assertEqual(Bill.objects.get(pk=bill2.pk).status, Bill.BillStatus.OVERDUE)
        self.assertEqual(
            Bill.objects.get(pk=bill3.pk).status, Bill.BillStatus.OVERDUE
        )  # No change
        self.assertEqual(
            Bill.objects.get(pk=bill4.pk).status, Bill.BillStatus.PENDING
        )  # No change
        self.assertEqual(Bill.objects.get(pk=bill5.pk).status, Bill.BillStatus.OVERDUE)


# --- Test NotifyOverdueBillsAPIView ---


class NotifyOverdueBillsAPITest(APITestCase):
    def setUp(self):
        self.client = APIRequestFactory()
        self.url = reverse("api:notify_overdue_bills")
        self.view = NotifyOverdueBillsAPIView.as_view()

        self.creditor1 = Creditor.objects.create(
            name="Test Creditor 1",
            city="Zurich",
            pcode="8000",
            country="CH",
            iban="CH41002721071046C2492",
            email="creditor@example.com",
        )
        self.creditor2 = Creditor.objects.create(
            name="Test Creditor 2",
            city="Zurich",
            pcode="8000",
            country="CH",
            iban="CH801503791J674321901",
            email="creditor2@example.com",
        )
        self.contact1 = Contact.objects.create(name="Con1", email="con1@example.com")
        self.contact2 = Contact.objects.create(name="Con2", email="con2@example.com")

        # Bills to test with
        self.overdue_bill1 = Bill.objects.create(
            creditor=self.creditor1,
            contact=self.contact1,
            amount=100,
            due_date=datetime.now(tz=timezone.utc) - timedelta(days=10),
            status=Bill.BillStatus.OVERDUE,
        )
        self.overdue_bill2 = Bill.objects.create(
            creditor=self.creditor2,
            contact=self.contact2,
            amount=200,
            due_date=datetime.now(tz=timezone.utc) - timedelta(days=5),
            status=Bill.BillStatus.OVERDUE,
        )
        self.pending_bill = Bill.objects.create(
            creditor=self.creditor1,
            contact=self.contact1,
            amount=50,
            due_date=datetime.now(tz=timezone.utc) + timedelta(days=5),
            status=Bill.BillStatus.PENDING,
        )
        self.paid_bill = Bill.objects.create(
            creditor=self.creditor2,
            contact=self.contact2,
            amount=75,
            due_date=datetime.now(tz=timezone.utc) - timedelta(days=15),
            status=Bill.BillStatus.PAID,
        )

    # Patch the send_overdue_email function where it is imported/used in NotifyOverdueBillsAPIView
    @mock.patch("send_bills.api.views.send_overdue_email")  # Adjust path
    def test_notify_overdue_bills_success(self, mock_send_overdue_email):
        # Simulate successful email sending for both overdue bills
        mock_send_overdue_email.return_value = 1

        response = self.view(self.client.post(self.url))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["message"], "sent overdue bill notifications")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(
            response.data["notifications"], 2
        )  # Two bills were overdue and should have been processed

        # Ensure send_overdue_email was called for the correct bills
        self.assertEqual(mock_send_overdue_email.call_count, 2)
        mock_send_overdue_email.assert_has_calls(
            [
                mock.call(self.overdue_bill1),
                mock.call(self.overdue_bill2),
            ],
            any_order=True,
        )

    @mock.patch("send_bills.api.views.send_overdue_email")
    def test_notify_overdue_bills_no_overdue_bills(self, mock_send_overdue_email):
        # Delete all overdue bills to test this scenario
        Bill.objects.filter(status=Bill.BillStatus.OVERDUE).delete()

        response = self.view(self.client.post(self.url))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["message"], "sent overdue bill notifications")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["notifications"], 0)  # No notifications sent

        # Ensure send_overdue_email was not called
        mock_send_overdue_email.assert_not_called()

    @mock.patch("send_bills.api.views.send_overdue_email")
    def test_notify_overdue_bills_some_failures(self, mock_send_overdue_email):
        # Simulate one success, one failure
        # The order depends on how .iterator() yields, but for two, it's predictable enough.
        # If many, you might need a more robust way to map calls.
        mock_send_overdue_email.side_effect = [
            1,
            0,
        ]  # First call succeeds, second fails

        response = self.view(self.client.post(self.url))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["message"], "sent overdue bill notifications")
        self.assertEqual(response.data["notifications"], 1)  # Only one succeeded

        # Check errors list (order may vary based on iterator)
        errors = response.data["errors"]
        self.assertEqual(len(errors), 1)
        # Check if the error message contains the expected bill
        # We don't know which bill failed, so check if any of the overdue bills are in the error message
        found_error_for_bill = False
        for error_msg in errors:
            if (
                str(self.overdue_bill1.pk) in error_msg
                or str(self.overdue_bill2.pk) in error_msg
            ):
                found_error_for_bill = True
                break
        self.assertTrue(found_error_for_bill)

        self.assertEqual(mock_send_overdue_email.call_count, 2)  # Both were attempted
