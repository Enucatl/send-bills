import datetime
from decimal import Decimal

import pandas as pd
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
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


@pytest.mark.django_db
def test_contact_creation():
    """Tests Contact model creation."""
    contact = Contact.objects.create(name="Jane Doe", email="jane.doe@example.com")
    assert contact.name == "Jane Doe"
    assert contact.email == "jane.doe@example.com"
    assert contact.created_at is not None


@pytest.mark.django_db
def test_contact_str_representation(contact_fixture):
    """Tests Contact model string representation."""
    assert str(contact_fixture) == "Contact A"


@pytest.mark.django_db
def test_contact_email_unique():
    """Tests that Contact email is unique."""
    mixer.blend(Contact, email="test@example.com")
    with pytest.raises(IntegrityError):
        Contact.objects.create(name="Another Contact", email="test@example.com")


@pytest.mark.django_db
def test_creditor_creation():
    """Tests Creditor model creation."""
    creditor = Creditor.objects.create(
        name="New Creditor",
        email="new@example.com",
        iban="IT60X0542811101000000123456",
        city="Geneva",
        country="CH",
        pcode="1200",
    )
    assert creditor.name == "New Creditor"
    assert creditor.email == "new@example.com"
    assert creditor.iban == "IT60X0542811101000000123456"
    assert creditor.created_at is not None


@pytest.mark.django_db
def test_creditor_str_representation(creditor_fixture):
    """Tests Creditor model string representation."""
    assert str(creditor_fixture) == "Test Creditor AG"


@pytest.mark.django_db
def test_creditor_iban_unique():
    """Tests that Creditor IBAN is unique."""
    mixer.blend(Creditor, iban="CH9300762011623852957")
    with pytest.raises(IntegrityError):
        Creditor.objects.create(
            name="Duplicate IBAN",
            email="duplicate@example.com",
            iban="CH9300762011623852957",
            city="Zurich",
            country="CH",
            pcode="8000",
        )


@pytest.mark.django_db
def test_creditor_clean_valid_iban():
    """Tests Creditor's clean method with a valid (but spaced) IBAN."""
    creditor_with_spaces = Creditor(
        name="Spacey Bank",
        email="spacey@example.com",
        iban="CH1499  403J1  M12OPJ2HC1",
        city="Basel",
        country="CH",
        pcode="4000",
    )
    creditor_with_spaces.full_clean()
    assert creditor_with_spaces.iban == "CH1499403J1M12OPJ2HC1"


@pytest.mark.django_db
def test_creditor_clean_invalid_iban():
    """Tests Creditor's clean method with an invalid IBAN."""
    creditor_invalid = Creditor(
        name="Invalid Bank",
        email="invalid@example.com",
        iban="INVALIDIBAN",
        city="Chur",
        country="CH",
        pcode="7000",
    )
    with pytest.raises(ValidationError, match="Invalid IBAN"):
        creditor_invalid.full_clean()


def test_get_date_offset_instance_valid_no_args():
    """Tests get_date_offset_instance with valid offsets and no arguments."""
    assert isinstance(get_date_offset_instance("MonthBegin"), pd.offsets.MonthBegin)
    assert isinstance(get_date_offset_instance("YearEnd"), pd.offsets.YearEnd)


def test_get_date_offset_instance_valid_with_args():
    """Tests get_date_offset_instance with valid offsets and arguments."""
    offset = get_date_offset_instance("BusinessDay", n=3)
    assert isinstance(offset, pd.offsets.BusinessDay)
    assert offset.n == 3
    offset = get_date_offset_instance("QuarterBegin", startingMonth=1)
    assert isinstance(offset, pd.offsets.QuarterBegin)
    assert offset.startingMonth == 1


def test_get_date_offset_instance_invalid_name():
    """Tests get_date_offset_instance with invalid offset names."""
    with pytest.raises(ValidationError, match="Invalid DateOffset name: NotAnOffset"):
        get_date_offset_instance("NotAnOffset")
    with pytest.raises(ValidationError, match="Invalid DateOffset name: Hour"):
        get_date_offset_instance("Hour")


def test_get_date_offset_instance_invalid_args():
    """Tests get_date_offset_instance with invalid arguments for an offset."""
    with pytest.raises(ValidationError, match="Invalid arguments for 'MonthEnd'"):
        get_date_offset_instance("MonthEnd", startingMonth=1)
    with pytest.raises(ValidationError, match="Invalid arguments for 'BusinessDay'"):
        get_date_offset_instance("BusinessDay", n="two")


@pytest.mark.django_db
def test_recurring_bill_creation_simple(
    mocker, contact_fixture, creditor_fixture, tzinfo
):
    """Tests simple RecurringBill creation. Uses mocker to patch timezone.now."""
    mock_time = datetime.datetime(2025, 1, 1, 0, 0, 0, tzinfo=tzinfo)
    mock_now = mocker.patch("django.utils.timezone.now", return_value=mock_time)
    rb = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="100.50",
        description_template="Monthly Subscription",
        frequency="MonthBegin",
        start_date=mock_time,
    )
    assert rb.frequency == "MonthBegin"
    assert rb.frequency_kwargs == {}
    assert rb.start_date == mock_time
    assert rb.next_billing_date == mock_time
    mock_now.assert_called_once()


@pytest.mark.django_db
def test_recurring_bill_creation_with_kwargs(
    mocker, contact_fixture, creditor_fixture, tzinfo
):
    """Tests RecurringBill creation with frequency kwargs."""
    mock_time = datetime.datetime(2025, 1, 1, 0, 0, 0, tzinfo=tzinfo)
    mock_now = mocker.patch("django.utils.timezone.now", return_value=mock_time)
    kwargs = {"n": 2, "normalize": True}
    rb = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="50.00",
        description_template="Bi-Weekly Fee",
        frequency="Week",
        frequency_kwargs=kwargs,
        start_date=mock_time,
    )
    assert rb.frequency == "Week"
    assert rb.frequency_kwargs == kwargs
    assert rb.next_billing_date == mock_time
    mock_now.assert_called_once()


@pytest.mark.django_db
def test_recurring_bill_clean_invalid_kwargs(
    mocker, contact_fixture, creditor_fixture, tzinfo
):
    """Tests RecurringBill's clean method with invalid frequency kwargs."""
    mock_time = datetime.datetime(2025, 1, 1, 0, 0, 0, tzinfo=tzinfo)
    mocker.patch("django.utils.timezone.now", return_value=mock_time)
    with pytest.raises(ValidationError) as excinfo:
        RecurringBill.objects.create(
            contact=contact_fixture,
            creditor=creditor_fixture,
            amount="99.00",
            description_template="Invalid Config",
            frequency="MonthEnd",
            frequency_kwargs={"invalid_arg": True},
            start_date=mock_time,
        )
    assert "frequency_kwargs" in excinfo.value.message_dict
    assert (
        "These arguments are not valid for the 'MonthEnd' offset."
        in excinfo.value.message_dict["frequency_kwargs"]
    )


@pytest.mark.django_db
def test_recurring_bill_save_past_next_billing_date(
    mocker, contact_fixture, creditor_fixture, tzinfo
):
    """Tests RecurringBill validation for next_billing_date in the past."""
    mock_time = datetime.datetime(2025, 7, 10, 10, 30, 0, tzinfo=tzinfo)
    mocker.patch("django.utils.timezone.now", return_value=mock_time)
    past_date = mock_time - datetime.timedelta(days=1)
    with pytest.raises(ValidationError, match="next_billing_date cannot be"):
        RecurringBill.objects.create(
            contact=contact_fixture,
            creditor=creditor_fixture,
            amount="10.00",
            description_template="Past Due Test",
            frequency="YearBegin",
            start_date=mock_time,
            next_billing_date=past_date,
        )


@pytest.mark.django_db
def test_recurring_bill_calculate_next_billing_date(
    mocker, contact_fixture, creditor_fixture, tzinfo
):
    """Tests RecurringBill's calculate_next_billing_date method."""
    base_date = datetime.datetime(2025, 7, 1, 10, 0, 0, tzinfo=tzinfo)
    mocker.patch("django.utils.timezone.now", return_value=base_date)
    rb_month = mixer.blend(
        RecurringBill,
        contact=contact_fixture,
        creditor=creditor_fixture,
        frequency="MonthEnd",
        start_date=base_date,
        next_billing_date=base_date,
    )
    expected_next = pd.Timestamp("2025-07-31 10:00:00", tz=tzinfo)
    assert rb_month.calculate_next_billing_date() == expected_next


def test_recurring_bill_frequency_choices():
    """Tests that RecurringBill's frequency choices match ALLOWED_DATE_OFFSETS."""
    field = RecurringBill._meta.get_field("frequency")
    choices = [choice[0] for choice in field.choices]
    assert set(choices) == set(ALLOWED_DATE_OFFSETS)


@pytest.mark.django_db
def test_recurring_bill_generate_bill(contact_fixture, creditor_fixture, tzinfo):
    """Tests RecurringBill's generate_bill method."""
    billing_date = datetime.datetime(2025, 4, 1, tzinfo=tzinfo)
    rb = RecurringBill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="99.99",
        description_template="Hosting for {{ billing_date.year }}Q{{ billing_date.quarter }}",
        frequency="QuarterBegin",
        start_date=billing_date,
        next_billing_date=billing_date,
    )
    new_bill = rb.generate_bill()
    assert isinstance(new_bill, Bill)
    assert new_bill.amount == Decimal("99.99")
    assert new_bill.recurring_bill == rb
    assert new_bill.billing_date == billing_date
    assert new_bill.additional_information == "Hosting for 2025Q2"


@pytest.mark.django_db
def test_bill_creation_and_defaults(contact_fixture, creditor_fixture):
    """Tests Bill creation with default date values."""
    time_before_creation = timezone.now()
    bill = Bill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="25.99",
        additional_information="One-off Internet Bill",
    )
    bill.refresh_from_db()
    time_delta = abs(bill.billing_date - time_before_creation)
    assert time_delta < datetime.timedelta(seconds=1)

    expected_due_date = bill.billing_date + pd.DateOffset(months=1)
    assert bill.due_date == expected_due_date
    assert bill.reference_number is not None
    assert bill.reference_number.startswith("RF")


@pytest.mark.django_db
def test_bill_creation_with_explicit_dates(contact_fixture, creditor_fixture, tzinfo):
    """Tests Bill creation with explicitly provided dates."""
    billing_date = datetime.datetime(2026, 1, 1, tzinfo=tzinfo)
    due_date = datetime.datetime(2026, 2, 15, tzinfo=tzinfo)
    bill = Bill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="50.00",
        additional_information="Manual Bill",
        billing_date=billing_date,
        due_date=due_date,
    )
    assert bill.billing_date == billing_date
    assert bill.due_date == due_date


@pytest.mark.django_db
def test_bill_foreign_keys_on_delete(contact_fixture, creditor_fixture, tzinfo):
    """
    Tests CASCADE behavior for foreign keys on Bill.
    Deleting contact/creditor while a Bill still references them should raise IntegrityError.
    """
    base_date = datetime.datetime(2025, 7, 1, tzinfo=tzinfo)
    recurring_bill = mixer.blend(
        RecurringBill,
        contact=contact_fixture,
        creditor=creditor_fixture,
        description_template="Test",
        amount="25.99",
        frequency="MonthBegin",
        start_date=base_date,
        next_billing_date=base_date,
    )
    bill = mixer.blend(
        Bill,
        contact=contact_fixture,
        creditor=creditor_fixture,
        recurring_bill=recurring_bill,
    )

    recurring_bill.delete()
    bill.refresh_from_db()
    assert bill.recurring_bill is None

    contact_to_delete = mixer.blend(Contact)
    creditor_to_delete = mixer.blend(Creditor)
    mixer.blend(Bill, contact=contact_to_delete, creditor=creditor_to_delete)

    with pytest.raises(IntegrityError):
        contact_to_delete.delete()
    with pytest.raises(IntegrityError):
        creditor_to_delete.delete()
