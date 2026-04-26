import logging

from django.core.management.base import BaseCommand

from send_bills.bills.services import process_bills

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process due recurring bills, pending bills, overdue bills, and reminders."

    def handle(self, *args, **options) -> None:
        summary = process_bills()
        generated = len(summary.generated_bills)
        sent_pending = len(summary.sent_pending_bills)
        marked_overdue = len(summary.marked_overdue_bills)
        overdue_notifications = len(summary.sent_overdue_notifications)

        self.stdout.write(
            self.style.SUCCESS(
                "Processed bills: "
                f"generated={generated}, "
                f"sent={sent_pending}, "
                f"marked_overdue={marked_overdue}, "
                f"overdue_notifications={overdue_notifications}"
            )
        )
        logger.info(
            "process_bills completed: generated=%s sent=%s marked_overdue=%s overdue_notifications=%s",
            generated,
            sent_pending,
            marked_overdue,
            overdue_notifications,
        )
