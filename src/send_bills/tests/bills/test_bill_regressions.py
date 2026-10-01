import importlib
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.forms import modelform_factory
from django.utils import timezone
from stdnum import iso11649

from send_bills.bills.models import Bill
from send_bills.bills.references import generate_invoice_reference


@pytest.mark.django_db
def test_new_references_are_distinct_and_issued_references_are_preserved(
    contact_fixture, creditor_fixture
):
    """Similar bills have distinct valid references that survive later edits."""
    bills = [
        Bill.objects.create(
            contact=contact_fixture,
            creditor=creditor_fixture,
            amount="20.00",
            additional_information=description,
        )
        for description in ("Rent household", "Rent garage")
    ]
    assert bills[0].reference_number != bills[1].reference_number
    for bill in bills:
        assert iso11649.is_valid(bill.reference_number)
        assert len(bill.reference_number) <= 25
        reference = bill.reference_number
        bill.additional_information = "Edited description"
        bill.save()
        bill.refresh_from_db()
        assert bill.reference_number == reference

    legacy_reference = "RF14YOUT20250401RICCARDO"
    bills[0].reference_number = legacy_reference
    bills[0].save()
    bills[0].refresh_from_db()
    assert bills[0].reference_number == legacy_reference


@pytest.mark.django_db
def test_reference_collision_rolls_back_bill_creation(
    contact_fixture, creditor_fixture, mocker
):
    """A legacy reference collision cannot leave an unreferenced bill behind."""
    reference = generate_invoice_reference("B123")
    Bill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="20.00",
        reference_number=reference,
    )
    mocker.patch.object(Bill, "_generate_reference_number", return_value=reference)
    with pytest.raises(ValidationError, match="already assigned"):
        Bill.objects.create(
            contact=contact_fixture, creditor=creditor_fixture, amount="20.00"
        )
    assert Bill.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("partial_save", [False, True])
def test_recording_payment_marks_bill_paid(
    contact_fixture, creditor_fixture, partial_save
):
    """Both a form save and a payment-only update persist paid status."""
    bill = Bill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="20.00",
        status=Bill.BillStatus.SENT,
    )
    paid_at = timezone.now()
    if partial_save:
        bill.paid_at = paid_at
        bill.save(update_fields=["paid_at"])
    else:
        form_type = modelform_factory(Bill, fields=["status", "paid_at"])
        form = form_type(
            {"status": Bill.BillStatus.SENT, "paid_at": paid_at.isoformat()},
            instance=bill,
        )
        assert form.is_valid(), form.errors
        form.save()
    bill.refresh_from_db()
    assert bill.status == Bill.BillStatus.PAID
    assert bill.paid_at == paid_at


@pytest.mark.django_db
def test_migration_repairs_payment_status_without_rewriting_history(
    contact_fixture, creditor_fixture
):
    """Existing payment dates are honored while unknown dates stay unknown."""
    bill = Bill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="20.00",
        reference_number="RF14YOUT20250401RICCARDO",
        status=Bill.BillStatus.SENT,
    )
    paid_at = timezone.now()
    Bill.objects.filter(pk=bill.pk).update(paid_at=paid_at)
    undated = Bill.objects.create(
        contact=contact_fixture,
        creditor=creditor_fixture,
        amount="20.00",
        status=Bill.BillStatus.PAID,
    )
    migration = importlib.import_module(
        "send_bills.bills.migrations.0011_reconcile_paid_bills"
    )
    migration.reconcile_paid_bills(apps, SimpleNamespace(connection=connection))
    bill.refresh_from_db()
    undated.refresh_from_db()
    assert bill.status == Bill.BillStatus.PAID
    assert bill.paid_at == paid_at
    assert bill.reference_number == "RF14YOUT20250401RICCARDO"
    assert undated.paid_at is None
