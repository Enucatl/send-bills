from __future__ import annotations

from decimal import Decimal

from django.core.management import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from send_bills.bills.models import Bill, Contact, Creditor
from send_bills.bills.utils import send_bill_email


class Command(BaseCommand):
    help = "Seed the dev database with a self-bill example."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--send-email",
            action="store_true",
            help="Send the example bill email after seeding the record.",
        )

    def handle(self, *args, **options) -> None:
        contact, _ = Contact.objects.get_or_create(
            email="matteo.abis@protonmail.com",
            defaults={"name": "Matteo Abis"},
        )
        creditor, _ = Creditor.objects.get_or_create(
            email="matteo.abis@protonmail.com",
            defaults={
                "name": "Matteo Abis",
                "city": "Zurich",
                "pcode": "8000",
                "country": "CH",
                "iban": "CH801503791J674321901",
            },
        )

        bill, created = Bill.objects.get_or_create(
            contact=contact,
            creditor=creditor,
            amount=Decimal("12.34"),
            currency="CHF",
            language="en",
            additional_information="Example self-bill for dev",
            defaults={
                "billing_date": timezone.now(),
                "status": Bill.BillStatus.PENDING,
            },
        )

        if not created and (
            bill.status != Bill.BillStatus.PENDING or bill.sent_at is not None
        ):
            bill.status = Bill.BillStatus.PENDING
            bill.sent_at = None
            bill.save(update_fields=["status", "sent_at"])

        subject = render_to_string(
            "emails/bill_subject.txt", context={"bill": bill}
        ).strip()
        body = render_to_string("emails/bill_body.txt", context={"bill": bill})

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded example bill {bill.id} with reference {bill.reference_number}."
            )
        )
        self.stdout.write(f"Contact: {contact.name} <{contact.email}>")
        self.stdout.write(f"Creditor: {creditor.name} <{creditor.email}>")
        self.stdout.write("Email preview:")
        self.stdout.write(f"Subject: {subject}")
        self.stdout.write(body)

        if options["send_email"]:
            try:
                sent_count = send_bill_email(bill)
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(
                    self.style.WARNING(f"Example email was not sent: {exc}")
                )
            else:
                if sent_count != 1:
                    self.stdout.write(
                        self.style.WARNING(
                            "Example email was not sent: "
                            f"send_bill_email returned {sent_count}."
                        )
                    )
                else:
                    bill.status = Bill.BillStatus.SENT
                    bill.sent_at = timezone.now()
                    bill.save(update_fields=["status", "sent_at"])
                    self.stdout.write(
                        self.style.SUCCESS("Example email sent successfully.")
                    )
