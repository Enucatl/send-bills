from decimal import Decimal
from io import StringIO

from django.core.management import call_command

from send_bills.bills.models import Bill, Contact, Creditor


def test_dev_seed_creates_example_bill(db):
    stdout = StringIO()

    call_command("dev_seed", stdout=stdout)

    contact = Contact.objects.get(email="matteo.abis@protonmail.com")
    creditor = Creditor.objects.get(email="matteo.abis@protonmail.com")
    bill = Bill.objects.get(
        contact=contact,
        creditor=creditor,
        amount=Decimal("12.34"),
        currency="CHF",
        language="en",
        additional_information="Example self-bill for dev",
    )

    assert bill.status == Bill.BillStatus.PENDING
    assert bill.sent_at is None

    output = stdout.getvalue()
    assert "Seeded example bill" in output
    assert "Email preview:" in output
    assert "Subject:" in output


def test_dev_seed_can_send_email(db, mocker):
    mock_send_bill_email = mocker.patch(
        "send_bills.bills.management.commands.dev_seed.send_bill_email", return_value=1
    )
    stdout = StringIO()

    call_command("dev_seed", "--send-email", stdout=stdout)

    bill = Bill.objects.get(
        additional_information="Example self-bill for dev",
        amount=Decimal("12.34"),
        currency="CHF",
        language="en",
    )

    assert mock_send_bill_email.call_count == 1
    assert bill.status == Bill.BillStatus.SENT
    assert bill.sent_at is not None
    assert "Example email sent successfully." in stdout.getvalue()
