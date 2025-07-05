import datetime
import io
import logging
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
from django.db import IntegrityError
from rest_framework.response import Response
from django.test import RequestFactory, TestCase
from django.utils import timezone

from send_bills.bills.models import (
    Bill,
    Contact,
    Creditor,
    RecurringBill,
    get_date_offset_instance,
)
from send_bills.api.views import GenerateRecurringBillsAPIView


class GenerateRecurringBillsViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = GenerateRecurringBillsAPIView.as_view()
        self.creditor = Creditor.objects.create(
            name="Test Creditor AG",
            city="Zurich",
            pcode="8000",
            country="CH",
            iban="CH9300772011623852957",  # Unique IBAN
            email="creditor@example.com",
        )
        self.contact = Contact.objects.create(
            name="Test Contact", email="contact@example.com"
        )
        self.tzinfo = datetime.timezone.utc

        # Configure logging to capture output
        self.logger = logging.getLogger("send_bills.api.views")
        self.log_stream = io.StringIO()
        self.handler = logging.StreamHandler(self.log_stream)
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.INFO)

    def tearDown(self):
        self.logger.removeHandler(self.handler)
        self.handler.close()  # Close the stream handler to prevent resource leaks

    @patch("send_bills.api.views.now")
    def test_no_active_recurring_bills_found(self, mock_now):
        """Test response when no recurring bills exist."""
        mock_now.return_value = timezone.datetime(
            2025, 1, 1, 10, 0, 0, tzinfo=self.tzinfo
        )

        request = self.factory.post("/api/generate-recurring-bills/")
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, Response)
        self.assertEqual(
            response.data,
            {
                "status": "success",
                "message": "No active recurring bills found to process.",
                "generated_count": 0,
            },
        )
        self.assertIn(
            "No active recurring bills found to process.", self.log_stream.getvalue()
        )
        self.assertEqual(Bill.objects.count(), 0)

    @patch("send_bills.api.views.now")
    def test_no_recurring_bills_due(self, mock_now):
        """Test response when active recurring bills exist but none are due."""
        current_time = timezone.datetime(2025, 7, 15, 12, 0, 0, tzinfo=self.tzinfo)
        mock_now.return_value = current_time

        # Create a recurring bill whose next_billing_date is in the future
        future_date = current_time + datetime.timedelta(days=10)
        recurring_bill = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="100.00",
            description_template="Future Bill {{ billing_date.month }}",
            frequency="MonthEnd",
            start_date=current_time,
            next_billing_date=future_date,
            is_active=True,
        )

        request = self.factory.post("/api/generate-recurring-bills/")
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, Response)
        self.assertIn(
            "No active recurring",
            response.data["message"],
        )
        self.assertIn(
            "No active recurring",
            self.log_stream.getvalue(),
        )
        self.assertEqual(Bill.objects.count(), 0)  # No bills should have been created
        # Ensure the recurring bill's next_billing_date was not altered
        recurring_bill.refresh_from_db()
        self.assertEqual(recurring_bill.next_billing_date, future_date)

    @patch("send_bills.api.views.now")
    def test_successful_bill_generation_single(self, mock_now):
        """Test successful generation of a single bill from a recurring schedule."""
        current_time = timezone.datetime(2025, 7, 20, 10, 0, 0, tzinfo=self.tzinfo)
        mock_now.return_value = current_time

        # Recurring bill is due (next_billing_date is in the past)
        due_date = current_time - datetime.timedelta(days=5)
        recurring_bill = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="150.00",
            description_template="Subscription for {{ billing_date.year }}-{{ billing_date.month }}",
            frequency="MonthBegin",  # Will advance to the next month's beginning
            frequency_kwargs={},
            start_date=due_date,
            next_billing_date=due_date,  # This is the "now" for which the bill is generated
            is_active=True,
        )

        request = self.factory.post("/api/generate-recurring-bills/")
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["generated_count"], 1)
        self.assertIn("Successfully generated 1 bills", response.data["message"])

        # Assert a new Bill was created
        self.assertEqual(Bill.objects.count(), 1)
        new_bill = Bill.objects.first()
        self.assertEqual(new_bill.contact, self.contact)
        self.assertEqual(new_bill.creditor, self.creditor)
        self.assertEqual(new_bill.amount, Decimal("150.00"))
        self.assertEqual(new_bill.status, Bill.BillStatus.PENDING)
        self.assertEqual(new_bill.recurring_bill, recurring_bill)
        # The billing_date should match the recurring_bill's next_billing_date *before* it was updated
        self.assertEqual(new_bill.billing_date, due_date)
        self.assertEqual(new_bill.additional_information, "Subscription for 2025-7")
        self.assertIsNotNone(new_bill.reference_number)

        # Assert recurring_bill's next_billing_date was updated
        recurring_bill.refresh_from_db()
        expected_next_billing_date = pd.Timestamp(due_date) + get_date_offset_instance(
            "MonthBegin"
        )
        self.assertEqual(recurring_bill.next_billing_date, expected_next_billing_date)
        self.assertIn("Generated new bill", self.log_stream.getvalue())
        self.assertIn(
            f"Next billing date set to {expected_next_billing_date.isoformat()}",
            self.log_stream.getvalue(),
        )

    @patch("send_bills.api.views.now")
    def test_successful_bill_generation_multiple_mixed(self, mock_now):
        """Test processing of multiple recurring bills, some due, some not."""
        current_time = timezone.datetime(2025, 7, 20, 10, 0, 0, tzinfo=self.tzinfo)
        mock_now.return_value = current_time

        # Recurring bill 1: Due
        rb1_due_date = current_time - datetime.timedelta(days=10)
        rb1 = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="20.00",
            description_template="Due Bill 1",
            frequency="Week",
            start_date=rb1_due_date,
            next_billing_date=rb1_due_date,
            is_active=True,
        )

        # Recurring bill 2: Not due (future date)
        rb2_future_date = current_time + datetime.timedelta(days=5)
        rb2 = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="30.00",
            description_template="Future Bill 2",
            frequency="MonthEnd",
            start_date=current_time,
            next_billing_date=rb2_future_date,
            is_active=True,
        )

        # Recurring bill 3: Due (exactly now)
        rb3_due_date = current_time
        rb3 = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="40.00",
            description_template="Due Bill 3",
            frequency="MonthBegin",
            start_date=rb3_due_date,
            next_billing_date=rb3_due_date,
            is_active=True,
        )

        # Recurring bill 4: Inactive, should be ignored
        rb4_inactive_date = current_time - datetime.timedelta(days=20)
        rb4 = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="50.00",
            description_template="Inactive Bill 4",
            frequency="Week",
            start_date=rb4_inactive_date,
            next_billing_date=rb4_inactive_date,
            is_active=False,  # This one is inactive
        )

        request = self.factory.post("/api/generate-recurring-bills/")
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(
            response.data["generated_count"], 2
        )  # Only rb1 and rb3 should generate
        self.assertIn("Successfully generated 2 bills", response.data["message"])

        self.assertEqual(Bill.objects.count(), 2)
        generated_bills = Bill.objects.all().order_by("amount")
        self.assertEqual(generated_bills[0].amount, Decimal("20.00"))  # Bill for rb1
        self.assertEqual(generated_bills[1].amount, Decimal("40.00"))  # Bill for rb3

        # Check rb1 state
        rb1.refresh_from_db()
        expected_rb1_next_date = pd.Timestamp(rb1_due_date) + get_date_offset_instance(
            "Week"
        )
        self.assertEqual(rb1.next_billing_date, expected_rb1_next_date)
        self.assertTrue(
            Bill.objects.filter(recurring_bill=rb1, billing_date=rb1_due_date).exists()
        )

        # Check rb2 state (should be unchanged)
        rb2.refresh_from_db()
        self.assertEqual(rb2.next_billing_date, rb2_future_date)
        self.assertFalse(Bill.objects.filter(recurring_bill=rb2).exists())

        # Check rb3 state
        rb3.refresh_from_db()
        expected_rb3_next_date = pd.Timestamp(rb3_due_date) + get_date_offset_instance(
            "MonthBegin"
        )
        self.assertEqual(rb3.next_billing_date, expected_rb3_next_date)
        self.assertTrue(
            Bill.objects.filter(recurring_bill=rb3, billing_date=rb3_due_date).exists()
        )

        # Check rb4 state (should be unchanged, no bill created)
        rb4.refresh_from_db()
        self.assertEqual(rb4.next_billing_date, rb4_inactive_date)
        self.assertFalse(Bill.objects.filter(recurring_bill=rb4).exists())

    @patch("send_bills.api.views.now")
    def test_error_during_bill_generation_or_update(self, mock_now):
        """Test error handling during the generation process."""
        current_time = timezone.datetime(2025, 8, 1, 10, 0, 0, tzinfo=self.tzinfo)
        mock_now.return_value = current_time

        # Recurring bill that will successfully generate
        rb_success_date = current_time - datetime.timedelta(days=1)
        rb_success = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="10.00",
            description_template="Successful Bill",
            frequency="MonthBegin",
            start_date=rb_success_date,
            next_billing_date=rb_success_date,
            is_active=True,
        )

        # Recurring bill that will cause an error during new_bill.save()
        # We need to mock the Bill save method to raise an error
        rb_fail_date = current_time - datetime.timedelta(days=2)
        rb_fail = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="20.00",
            description_template="Failing Bill",
            frequency="MonthBegin",
            start_date=rb_fail_date,
            next_billing_date=rb_fail_date,
            is_active=True,
        )

        # Patch Bill.save() to raise an exception for the 'Failing Bill' amount
        original_bill_save = Bill.save

        def mock_bill_save(self):
            if self.amount == Decimal("20.00"):
                raise IntegrityError("Simulated database error during Bill save")
            return original_bill_save(self)

        with patch("send_bills.bills.models.Bill.save", new=mock_bill_save):
            request = self.factory.post("/api/generate-recurring-bills/")
            response = self.view(request)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["status"], "partial_success")
            self.assertEqual(response.data["generated_count"], 1)  # Only rb_success
            self.assertEqual(len(response.data["errors"]), 1)
            self.assertIn(f"RecurringBill {rb_fail.id}", response.data["errors"][0])
            self.assertIn("Simulated database error", response.data["errors"][0])

            # Verify only one bill was actually created (the successful one)
            self.assertEqual(Bill.objects.count(), 1)
            self.assertTrue(Bill.objects.filter(recurring_bill=rb_success).exists())
            self.assertFalse(Bill.objects.filter(recurring_bill=rb_fail).exists())

            # Verify rb_success was updated
            rb_success.refresh_from_db()
            expected_rb_success_next_date = pd.Timestamp(
                rb_success_date
            ) + get_date_offset_instance("MonthBegin")
            self.assertEqual(
                rb_success.next_billing_date, expected_rb_success_next_date
            )

            # Verify rb_fail was NOT updated due to transaction rollback
            rb_fail.refresh_from_db()
            self.assertEqual(rb_fail.next_billing_date, rb_fail_date)

            self.assertIn(
                f"Unexpected error processing RecurringBill {rb_fail.id}",
                self.log_stream.getvalue(),
            )
            self.assertIn(
                "Simulated database error during Bill save", self.log_stream.getvalue()
            )

        # Restore original save method
        Bill.save = original_bill_save

    @patch("send_bills.api.views.now")
    def test_next_billing_date_exactly_now(self, mock_now):
        """Ensure bills are generated when next_billing_date is exactly the current time."""
        current_time = timezone.datetime(2025, 9, 1, 10, 30, 0, tzinfo=self.tzinfo)
        mock_now.return_value = current_time

        rb = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="75.00",
            description_template="Exact Time Bill",
            frequency="MonthBegin",
            start_date=current_time,
            next_billing_date=current_time,
            is_active=True,
        )

        request = self.factory.post("/api/generate-recurring-bills/")
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["generated_count"], 1)

        self.assertEqual(Bill.objects.count(), 1)
        new_bill = Bill.objects.first()
        self.assertEqual(new_bill.amount, Decimal("75.00"))
        self.assertEqual(new_bill.billing_date, current_time)

        rb.refresh_from_db()
        expected_next_date = pd.Timestamp(current_time) + get_date_offset_instance(
            "MonthBegin"
        )
        self.assertEqual(rb.next_billing_date, expected_next_date)
