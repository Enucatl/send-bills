"""Regression checks for payment imports and their admin form."""

import io
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.db import connection
from django.test import RequestFactory

from send_bills.bills.admin import CreditorAdmin
from send_bills.bills.models import Bill, Creditor
from send_bills.bills.utils import process_payments


def payment_csv(*payments: tuple[str, str, str, str, str]) -> io.BytesIO:
    """Build a minimal bank export from date, reference, IBAN, amount, currency."""
    rows = ["metadata;value"] * 8
    rows.append("Data dell'operazione;Descrizione1;Descrizione2;Importo singolo;Moneta")
    rows.extend(
        f"{date};SCOR: {reference};{iban};{amount};{currency}"
        for date, reference, iban, amount, currency in payments
    )
    return io.BytesIO("\n".join(rows).encode())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "duplicate_fields",
    [
        {},
        {"status": Bill.BillStatus.PAID},
        {"amount": Decimal("100.00")},
        {"currency": "EUR"},
    ],
)
def test_import_rejects_ambiguous_reference(
    contact_fixture, creditor_fixture, duplicate_fields
):
    """A colliding reference never settles either bill, including on reimport."""
    fields = {
        "contact": contact_fixture,
        "creditor": creditor_fixture,
        "amount": Decimal("20.40"),
        "additional_information": "Rent",
        "reference_number": "RF29RENT20260901FRIENDEXA",
        "status": Bill.BillStatus.SENT,
    }
    bill = Bill.objects.create(**fields)
    duplicate = Bill.objects.create(**(fields | duplicate_fields))
    with pytest.raises(ValueError, match="Multiple bills share payment reference"):
        process_payments(
            payment_csv(
                (
                    "2026-09-02",
                    bill.reference_number,
                    creditor_fixture.iban,
                    "20.40",
                    "CHF",
                )
            )
        )
    bill.refresh_from_db()
    duplicate.refresh_from_db()
    assert bill.status == Bill.BillStatus.SENT
    assert bill.paid_at is None
    assert duplicate.status == duplicate_fields.get("status", Bill.BillStatus.SENT)


@pytest.mark.django_db(transaction=True)
def test_import_rolls_back_earlier_payments(contact_fixture, creditor_fixture):
    """Malformed later rows roll back earlier payments from autocommit mode."""
    bills = [
        Bill.objects.create(
            contact=contact_fixture,
            creditor=creditor_fixture,
            amount=Decimal("20.40"),
            additional_information=f"Rent {index}",
            reference_number=f"TEST{index}",
            status=Bill.BillStatus.SENT,
        )
        for index in range(2)
    ]
    assert connection.get_autocommit()
    with pytest.raises(ValueError, match="not-a-date"):
        process_payments(
            payment_csv(
                (
                    "2026-09-02",
                    bills[0].reference_number,
                    creditor_fixture.iban,
                    "20.40",
                    "CHF",
                ),
                (
                    "not-a-date",
                    bills[1].reference_number,
                    creditor_fixture.iban,
                    "20.40",
                    "CHF",
                ),
            )
        )
    for bill in bills:
        bill.refresh_from_db()
        assert bill.status == Bill.BillStatus.SENT
        assert bill.paid_at is None


@pytest.mark.django_db
@pytest.mark.parametrize("amount,currency", [("99.00", "CHF"), ("20.40", "EUR")])
def test_import_ignores_mismatched_amount_or_currency(
    contact_fixture, creditor_fixture, amount, currency
):
    """Unique references still require the billed amount and currency."""
    bill = Bill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount=Decimal("20.40"),
        additional_information="Rent",
        status=Bill.BillStatus.SENT,
    )
    assert (
        process_payments(
            payment_csv(
                (
                    "2026-09-02",
                    bill.reference_number,
                    creditor_fixture.iban,
                    amount,
                    currency,
                )
            )
        )
        == 0
    )
    bill.refresh_from_db()
    assert bill.status == Bill.BillStatus.SENT
    assert bill.paid_at is None


@pytest.mark.django_db
def test_import_preserves_existing_payment_date(contact_fixture, creditor_fixture):
    """An inconsistent legacy status cannot overwrite a recorded payment date."""
    paid_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    bill = Bill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount=Decimal("20.40"),
        additional_information="Rent",
        status=Bill.BillStatus.SENT,
    )
    Bill.objects.filter(pk=bill.pk).update(paid_at=paid_at)
    assert (
        process_payments(
            payment_csv(
                (
                    "2026-09-02",
                    bill.reference_number,
                    creditor_fixture.iban,
                    "20.40",
                    "CHF",
                )
            )
        )
        == 0
    )
    bill.refresh_from_db()
    assert bill.paid_at == paid_at


def test_invalid_upload_preserves_form_errors():
    """Missing files remain bound to the form with a visible field error."""
    request = RequestFactory().post("/admin/bills/creditor/upload-csv/", {})
    creditor_admin = CreditorAdmin(Creditor, admin.site)
    with (
        patch.object(creditor_admin, "has_add_permission", return_value=True),
        patch("send_bills.bills.admin.render") as render,
    ):
        creditor_admin.upload_csv(request)
    form = render.call_args.args[2]["form"]
    assert form.is_bound
    assert form.errors["csv_file"] == ["This field is required."]
