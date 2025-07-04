import datetime
from decimal import Decimal

from unittest.mock import patch

import pandas as pd
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from mixer.backend.django import mixer

from send_bills.bills.models import (
    ALLOWED_DATE_OFFSETS,
    Bill,
    Contact,
    Creditor,
    RecurringBill,
    get_date_offset_instance,
)


class ModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.contact = mixer.blend(
            Contact, name="Test Contact", email="test@example.com"
        )
        cls.creditor = mixer.blend(
            Creditor,
            name="Test Creditor",
            email="creditor@example.com",
            iban="CH9300762011623852957",
            city="Bern",
            country="CH",
            pcode="3000",
        )
        cls.tzinfo = datetime.timezone.utc

    def test_contact_creation(self):
        contact = Contact.objects.create(name="Jane Doe", email="jane.doe@example.com")
        self.assertEqual(contact.name, "Jane Doe")
        self.assertEqual(contact.email, "jane.doe@example.com")
        self.assertIsNotNone(contact.created_at)

    def test_contact_str_representation(self):
        self.assertEqual(str(self.contact), "Test Contact")

    def test_contact_email_unique(self):
        with self.assertRaises(IntegrityError):
            Contact.objects.create(name="Another Contact", email="test@example.com")

    def test_creditor_creation(self):
        creditor = Creditor.objects.create(
            name="New Creditor",
            email="new@example.com",
            iban="IT60X0542811101000000123456",
            city="Geneva",
            country="CH",
            pcode="1200",
        )
        self.assertEqual(creditor.name, "New Creditor")
        self.assertEqual(creditor.email, "new@example.com")
        self.assertEqual(creditor.iban, "IT60X0542811101000000123456")
        self.assertIsNotNone(creditor.created_at)

    def test_creditor_str_representation(self):
        self.assertEqual(str(self.creditor), "Test Creditor")

    def test_creditor_iban_unique(self):
        with self.assertRaises(IntegrityError):
            Creditor.objects.create(
                name="Duplicate IBAN",
                email="duplicate@example.com",
                iban="CH9300762011623852957",
                city="Zurich",
                country="CH",
                pcode="8000",
            )

    def test_creditor_clean_valid_iban(self):
        creditor_with_spaces = Creditor(
            name="Spacey Bank",
            email="spacey@example.com",
            iban="BR15 00000 00000 00109 32840 814P2",
            city="Basel",
            country="CH",
            pcode="4000",
        )
        creditor_with_spaces.full_clean()
        self.assertEqual(creditor_with_spaces.iban, "BR1500000000000010932840814P2")

    def test_creditor_clean_invalid_iban(self):
        creditor_invalid = Creditor(
            name="Invalid Bank",
            email="invalid@example.com",
            iban="INVALIDIBAN",
            city="Chur",
            country="CH",
            pcode="7000",
        )
        with self.assertRaisesRegex(ValidationError, "Invalid IBAN"):
            creditor_invalid.full_clean()

    def test_get_date_offset_instance_valid_no_args(self):
        self.assertIsInstance(
            get_date_offset_instance("MonthBegin"), pd.offsets.MonthBegin
        )
        self.assertIsInstance(get_date_offset_instance("YearEnd"), pd.offsets.YearEnd)

    def test_get_date_offset_instance_valid_with_args(self):
        offset = get_date_offset_instance("BusinessDay", n=3)
        self.assertIsInstance(offset, pd.offsets.BusinessDay)
        self.assertEqual(offset.n, 3)
        offset = get_date_offset_instance("QuarterBegin", startingMonth=1)
        self.assertIsInstance(offset, pd.offsets.QuarterBegin)
        self.assertEqual(offset.startingMonth, 1)

    def test_get_date_offset_instance_invalid_name(self):
        with self.assertRaisesMessage(
            ValidationError, "Invalid DateOffset name: NotAnOffset"
        ):
            get_date_offset_instance("NotAnOffset")
        with self.assertRaisesMessage(ValidationError, "Invalid DateOffset name: Hour"):
            get_date_offset_instance("Hour")

    def test_get_date_offset_instance_invalid_args(self):
        with self.assertRaisesRegex(
            ValidationError, "Invalid arguments for 'MonthEnd'"
        ):
            get_date_offset_instance("MonthEnd", startingMonth=1)
        with self.assertRaisesRegex(
            ValidationError, "Invalid arguments for 'BusinessDay'"
        ):
            get_date_offset_instance("BusinessDay", n="two")

    @patch("django.utils.timezone.now")
    def test_recurring_bill_creation_simple(self, mock_now):
        mock_time = datetime.datetime(2025, 1, 1, 0, 0, 0, tzinfo=self.tzinfo)
        mock_now.return_value = mock_time
        rb = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="100.50",
            description_template="Monthly Subscription",
            frequency="MonthBegin",
            start_date=mock_time,
        )
        self.assertEqual(rb.frequency, "MonthBegin")
        self.assertEqual(rb.frequency_kwargs, {})
        self.assertEqual(rb.start_date, mock_time)
        self.assertEqual(rb.next_billing_date, mock_time)

    @patch("django.utils.timezone.now")
    def test_recurring_bill_creation_with_kwargs(self, mock_now):
        mock_time = datetime.datetime(2025, 1, 1, 0, 0, 0, tzinfo=self.tzinfo)
        mock_now.return_value = mock_time
        kwargs = {"n": 2, "normalize": True}
        rb = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="50.00",
            description_template="Bi-Weekly Fee",
            frequency="Week",
            frequency_kwargs=kwargs,
            start_date=mock_time,
        )
        self.assertEqual(rb.frequency, "Week")
        self.assertEqual(rb.frequency_kwargs, kwargs)
        self.assertEqual(rb.next_billing_date, mock_time)

    @patch("django.utils.timezone.now")
    def test_recurring_bill_clean_invalid_kwargs(self, mock_now):
        mock_time = datetime.datetime(2025, 1, 1, 0, 0, 0, tzinfo=self.tzinfo)
        mock_now.return_value = mock_time
        with self.assertRaises(ValidationError) as cm:
            RecurringBill.objects.create(
                contact=self.contact,
                creditor=self.creditor,
                amount="99.00",
                description_template="Invalid Config",
                frequency="MonthEnd",
                frequency_kwargs={"invalid_arg": True},
                start_date=mock_time,
            )
        self.assertIn("frequency_kwargs", cm.exception.message_dict)
        self.assertIn(
            "These arguments are not valid for the 'MonthEnd' offset.",
            cm.exception.message_dict["frequency_kwargs"],
        )

    @patch("django.utils.timezone.now")
    def test_recurring_bill_save_past_next_billing_date(self, mock_now):
        mock_time = datetime.datetime(2025, 7, 10, 10, 30, 0, tzinfo=self.tzinfo)
        mock_now.return_value = mock_time
        past_date = mock_time - datetime.timedelta(days=1)
        with self.assertRaisesRegex(ValidationError, "next_billing_date cannot be"):
            RecurringBill.objects.create(
                contact=self.contact,
                creditor=self.creditor,
                amount="10.00",
                description_template="Past Due Test",
                frequency="YearBegin",
                start_date=mock_time,
                next_billing_date=past_date,
            )

    @patch("django.utils.timezone.now")
    def test_recurring_bill_calculate_next_billing_date(self, mock_now):
        base_date = datetime.datetime(2025, 7, 1, 10, 0, 0, tzinfo=self.tzinfo)
        mock_now.return_value = base_date
        rb_month = mixer.blend(
            RecurringBill,
            frequency="MonthEnd",
            start_date=base_date,
            next_billing_date=base_date,
        )
        expected_next = pd.Timestamp("2025-07-31 10:00:00", tz=self.tzinfo)
        self.assertEqual(rb_month.calculate_next_billing_date(), expected_next)

    def test_recurring_bill_frequency_choices(self):
        field = RecurringBill._meta.get_field("frequency")
        choices = [choice[0] for choice in field.choices]
        self.assertSetEqual(set(choices), set(ALLOWED_DATE_OFFSETS))

    def test_recurring_bill_generate_bill(self):
        billing_date = datetime.datetime(2025, 4, 1, tzinfo=self.tzinfo)
        rb = RecurringBill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="99.99",
            description_template="Hosting for {{ billing_date.year }}Q{{ billing_date.quarter }}",
            frequency="QuarterBegin",
            start_date=billing_date,
            next_billing_date=billing_date,
        )
        new_bill = rb.generate_bill()
        self.assertIsInstance(new_bill, Bill)
        self.assertEqual(new_bill.amount, Decimal("99.99"))
        self.assertEqual(new_bill.recurring_bill, rb)
        self.assertEqual(new_bill.billing_date, billing_date)
        self.assertEqual(new_bill.additional_information, "Hosting for 2025Q2")

    def test_bill_creation_and_defaults(self):
        time_before_creation = timezone.now()
        bill = Bill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="25.99",
            additional_information="One-off Internet Bill",
        )
        bill.refresh_from_db()
        self.assertAlmostEqual(
            bill.billing_date,
            time_before_creation,
            delta=datetime.timedelta(seconds=1),
        )
        expected_due_date = bill.billing_date + pd.DateOffset(months=1)
        self.assertEqual(bill.due_date, expected_due_date)
        self.assertIsNotNone(bill.reference_number)
        self.assertTrue(bill.reference_number.startswith("RF"))

    def test_bill_creation_with_explicit_dates(self):
        billing_date = datetime.datetime(2026, 1, 1, tzinfo=self.tzinfo)
        due_date = datetime.datetime(2026, 2, 15, tzinfo=self.tzinfo)
        bill = Bill.objects.create(
            contact=self.contact,
            creditor=self.creditor,
            amount="50.00",
            additional_information="Manual Bill",
            billing_date=billing_date,
            due_date=due_date,
        )
        self.assertEqual(bill.billing_date, billing_date)
        self.assertEqual(bill.due_date, due_date)

    def test_bill_foreign_keys_on_delete(self):
        base_date = datetime.datetime(2025, 7, 1, tzinfo=self.tzinfo)
        recurring_bill = mixer.blend(
            RecurringBill,
            description_template="Test",
            amount="25.99",
            frequency="MonthBegin",
            start_date=base_date,
            next_billing_date=base_date,
        )
        bill = mixer.blend(
            Bill,
            contact=self.contact,
            creditor=self.creditor,
            recurring_bill=recurring_bill,
        )
        recurring_bill.delete()
        bill.refresh_from_db()
        self.assertIsNone(bill.recurring_bill)
        with self.assertRaises(IntegrityError):
            self.contact.delete()
        with self.assertRaises(IntegrityError):
            self.creditor.delete()
