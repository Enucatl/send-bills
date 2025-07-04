import io
import json
import logging
from datetime import timedelta
from unittest import mock
from unittest.mock import patch

from django.http import JsonResponse
from django.test import RequestFactory, TestCase
from django.utils import timezone

# Adjust these imports based on your actual app name
from send_bills.bills.models import Bill, Contact, Creditor

# Import send_bill_email from utils, and send_pending_bills_api_view from views
from send_bills.bills.utils import send_bill_email
from send_bills.bills.views import send_pending_bills_api_view


class BillProcessingViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.creditor = Creditor.objects.create(
            name="Test Creditor AG",
            city="Zurich",
            pcode="8000",
            country="CH",
            iban="CH9300762011623852957",
            email="creditor@example.com",
        )
        self.contact = Contact.objects.create(
            name="Test Contact", email="contact@example.com"
        )

        self.bill_pending_1 = Bill.objects.create(
            creditor=self.creditor,
            contact=self.contact,
            amount=100.50,
            currency="CHF",
            status=Bill.BillStatus.PENDING,
        )
        self.bill_pending_2 = Bill.objects.create(
            creditor=self.creditor,
            contact=self.contact,
            amount=200.75,
            currency="CHF",
            status=Bill.BillStatus.PENDING,
        )
        self.bill_sent = Bill.objects.create(
            creditor=self.creditor,
            contact=self.contact,
            amount=50.00,
            currency="CHF",
            status=Bill.BillStatus.SENT,
            sent_at=timezone.now(),
        )

        # Configure logging to capture output
        self.logger = logging.getLogger("send_bills.bills.views")
        self.log_stream = io.StringIO()
        self.handler = logging.StreamHandler(self.log_stream)
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.INFO)

    def tearDown(self):
        self.logger.removeHandler(self.handler)

    # --- Tests for send_pending_bills_api_view ---

    def test_only_post_requests_allowed(self):
        request = self.factory.get("/api/send_bills/")  # Use a dummy URL
        response = send_pending_bills_api_view(request)
        self.assertEqual(response.status_code, 405)
        self.assertIsInstance(response, JsonResponse)
        self.assertIn("Only POST requests are allowed", response.content.decode())

    @patch(
        "send_bills.bills.views.send_bill_email"
    )  # Patch the imported function in the view's module
    def test_no_pending_bills_found(self, mock_send_bill_email):
        # Ensure no pending bills exist for this test
        Bill.objects.filter(status=Bill.BillStatus.PENDING).delete()

        request = self.factory.post("/api/send_bills/")
        response = send_pending_bills_api_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(
            json.loads(response.content.decode()),
            {
                "status": "success",
                "message": "No pending bills found to send.",
                "processed_count": 0,
            },
        )
        mock_send_bill_email.assert_not_called()
        self.assertIn("No pending bills found to send.", self.log_stream.getvalue())

    @patch(
        "send_bills.bills.views.send_bill_email", return_value=1
    )  # Mock send_bill_email to always succeed
    def test_successful_sending_of_all_pending_bills(self, mock_send_bill_email):
        request = self.factory.post("/api/send_bills/")
        response = send_pending_bills_api_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(
            json.loads(response.content.decode()),
            {
                "status": "success",
                "message": f"Successfully sent and updated 2 pending bills.",
                "processed_count": 2,
            },
        )

        # Assert send_bill_email was called for each pending bill
        self.assertEqual(mock_send_bill_email.call_count, 2)
        mock_send_bill_email.assert_has_calls(
            [mock.call(self.bill_pending_1), mock.call(self.bill_pending_2)],
            any_order=True,
        )

        # Assert bill statuses are updated
        self.bill_pending_1.refresh_from_db()
        self.assertEqual(self.bill_pending_1.status, Bill.BillStatus.SENT)
        self.assertIsNotNone(self.bill_pending_1.sent_at)
        self.assertLess(
            timezone.now() - self.bill_pending_1.sent_at, timedelta(seconds=5)
        )  # Check it's recent

        self.bill_pending_2.refresh_from_db()
        self.assertEqual(self.bill_pending_2.status, Bill.BillStatus.SENT)
        self.assertIsNotNone(self.bill_pending_2.sent_at)
        self.assertLess(
            timezone.now() - self.bill_pending_2.sent_at, timedelta(seconds=5)
        )

        self.bill_sent.refresh_from_db()  # Ensure non-pending bills are not touched
        self.assertEqual(self.bill_sent.status, Bill.BillStatus.SENT)
        self.assertIn(f"Bill {self.bill_pending_1.id}", self.log_stream.getvalue())
        self.assertIn(f"Bill {self.bill_pending_2.id}", self.log_stream.getvalue())

    @patch("send_bills.bills.views.send_bill_email")
    def test_partial_success_with_some_failures(self, mock_send_bill_email):
        # Configure mock_send_bill_email to succeed for bill_pending_1, fail for bill_pending_2
        mock_send_bill_email.side_effect = [
            1,
            0,
        ]  # 1 for bill_pending_1, 0 for bill_pending_2 (order matters if not using specific bill mocks)

        request = self.factory.post("/api/send_bills/")
        response = send_pending_bills_api_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, JsonResponse)
        json_response = json.loads(response.content.decode())
        self.assertEqual(json_response["status"], "partial_success")
        self.assertEqual(json_response["processed_count"], 1)
        self.assertEqual(len(json_response["errors"]), 1)
        self.assertIn(f"Bill {self.bill_pending_2.id}", json_response["errors"][0])

        # Assert bill statuses
        self.bill_pending_1.refresh_from_db()
        self.assertEqual(self.bill_pending_1.status, Bill.BillStatus.SENT)
        self.assertIsNotNone(self.bill_pending_1.sent_at)

        self.bill_pending_2.refresh_from_db()
        self.assertEqual(
            self.bill_pending_2.status, Bill.BillStatus.PENDING
        )  # Should not be updated
        self.assertIsNone(self.bill_pending_2.sent_at)

        self.assertIn(
            f"Failed to send and update status for bill {self.bill_pending_2.id}",
            self.log_stream.getvalue(),
        )

    @patch("send_bills.bills.views.send_bill_email")
    def test_unexpected_exception_during_processing(self, mock_send_bill_email):
        # Make the first call succeed, the second call raise an exception
        mock_send_bill_email.side_effect = [1, Exception("Simulated network error")]

        request = self.factory.post("/api/send_bills/")
        response = send_pending_bills_api_view(request)

        self.assertEqual(response.status_code, 200)
        json_response = json.loads(response.content.decode())
        self.assertEqual(json_response["status"], "partial_success")
        self.assertEqual(json_response["processed_count"], 1)
        self.assertEqual(len(json_response["errors"]), 1)
        self.assertIn(f"Bill {self.bill_pending_2.id}", json_response["errors"][0])
        self.assertIn(
            "Unexpected error - Simulated network error", json_response["errors"][0]
        )

        # Assert bill statuses
        self.bill_pending_1.refresh_from_db()
        self.assertEqual(self.bill_pending_1.status, Bill.BillStatus.SENT)
        self.assertIsNotNone(self.bill_pending_1.sent_at)

        self.bill_pending_2.refresh_from_db()
        self.assertEqual(
            self.bill_pending_2.status, Bill.BillStatus.PENDING
        )  # Should not be updated
        self.assertIsNone(self.bill_pending_2.sent_at)

        self.assertIn(
            f"Unexpected error processing bill {self.bill_pending_2.id}",
            self.log_stream.getvalue(),
        )
        self.assertIn("Simulated network error", self.log_stream.getvalue())
