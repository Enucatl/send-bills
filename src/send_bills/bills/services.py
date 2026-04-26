from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Literal

from django.db import connection, transaction
from django.db.models import F, Q, QuerySet
from django.utils import timezone

from send_bills.bills.models import Bill, RecurringBill
from send_bills.bills.utils import send_bill_email, send_overdue_email

logger = logging.getLogger(__name__)

LifecycleStatus = Literal["processed", "skipped", "error"]
OVERDUE_NOTIFICATION_INTERVAL = timedelta(days=7)


@dataclass(slots=True)
class LifecycleResult:
    object_id: int
    status: LifecycleStatus
    message: str
    related_object_id: int | None = None


@dataclass(slots=True)
class ProcessBillsSummary:
    generated_bills: list[LifecycleResult]
    sent_pending_bills: list[LifecycleResult]
    marked_overdue_bills: list[LifecycleResult]
    sent_overdue_notifications: list[LifecycleResult]


def _apply_skip_locked(queryset: QuerySet) -> QuerySet:
    if connection.features.has_select_for_update_skip_locked:
        return queryset.select_for_update(skip_locked=True)
    return queryset.select_for_update()


def _log_results(action: str, results: list[LifecycleResult]) -> None:
    for result in results:
        if result.status == "error":
            logger.error(
                "%s failed for %s: %s", action, result.object_id, result.message
            )
        elif result.status == "processed":
            logger.info(
                "%s processed for %s: %s", action, result.object_id, result.message
            )
        else:
            logger.info(
                "%s skipped for %s: %s", action, result.object_id, result.message
            )


def generate_due_recurring_bills(
    current_time: datetime | None = None,
) -> list[LifecycleResult]:
    now = current_time or timezone.now()
    results: list[LifecycleResult] = []
    recurring_bill_ids = list(
        RecurringBill.objects.filter(is_active=True, next_billing_date__lte=now)
        .order_by("next_billing_date", "pk")
        .values_list("pk", flat=True)
    )

    for recurring_bill_id in recurring_bill_ids:
        try:
            with transaction.atomic():
                recurring_bill = _apply_skip_locked(
                    RecurringBill.objects.select_related("contact", "creditor").filter(
                        pk=recurring_bill_id
                    )
                ).get()
                if recurring_bill.next_billing_date > now:
                    results.append(
                        LifecycleResult(
                            recurring_bill.id,
                            "skipped",
                            "Recurring bill is no longer due.",
                        )
                    )
                    continue

                new_bill = recurring_bill.generate_bill()
                new_bill.save()
                recurring_bill.next_billing_date = (
                    recurring_bill.calculate_next_billing_date()
                )
                recurring_bill.save(update_fields=["next_billing_date"])
                results.append(
                    LifecycleResult(
                        recurring_bill.id,
                        "processed",
                        f"Generated bill {new_bill.id}.",
                        related_object_id=new_bill.id,
                    )
                )
        except Exception as exc:  # pragma: no cover - exercised in tests
            results.append(LifecycleResult(recurring_bill_id, "error", str(exc)))

    _log_results("generate_due_recurring_bills", results)
    return results


def send_pending_bills(current_time: datetime | None = None) -> list[LifecycleResult]:
    now = current_time or timezone.now()
    results: list[LifecycleResult] = []
    pending_bill_ids = list(
        Bill.objects.filter(status=Bill.BillStatus.PENDING)
        .order_by("billing_date", "pk")
        .values_list("pk", flat=True)
    )

    for bill_id in pending_bill_ids:
        try:
            with transaction.atomic():
                bill = _apply_skip_locked(
                    Bill.objects.select_related("contact", "creditor").filter(
                        pk=bill_id
                    )
                ).get()
                if bill.status != Bill.BillStatus.PENDING:
                    results.append(
                        LifecycleResult(
                            bill.id,
                            "skipped",
                            "Bill is no longer pending.",
                        )
                    )
                    continue

                email_sent_count = send_bill_email(bill)
                if email_sent_count != 1:
                    results.append(
                        LifecycleResult(
                            bill.id,
                            "error",
                            f"Failed to send email (returned {email_sent_count}).",
                        )
                    )
                    continue

                bill.status = Bill.BillStatus.SENT
                bill.sent_at = now
                bill.save(update_fields=["status", "sent_at"])
                results.append(
                    LifecycleResult(
                        bill.id,
                        "processed",
                        "Bill status updated to SENT.",
                    )
                )
        except Exception as exc:  # pragma: no cover - exercised in tests
            results.append(LifecycleResult(bill_id, "error", str(exc)))

    _log_results("send_pending_bills", results)
    return results


def mark_overdue_bills(current_time: datetime | None = None) -> list[LifecycleResult]:
    now = current_time or timezone.now()
    results: list[LifecycleResult] = []
    overdue_bill_ids = list(
        Bill.objects.filter(due_date__lte=now)
        .exclude(status__in=[Bill.BillStatus.OVERDUE, Bill.BillStatus.PAID])
        .order_by("due_date", "pk")
        .values_list("pk", flat=True)
    )

    for bill_id in overdue_bill_ids:
        updated = (
            Bill.objects.filter(
                pk=bill_id,
                due_date__lte=now,
            )
            .exclude(status__in=[Bill.BillStatus.OVERDUE, Bill.BillStatus.PAID])
            .update(status=Bill.BillStatus.OVERDUE)
        )
        if updated:
            results.append(
                LifecycleResult(bill_id, "processed", "Bill status updated to OVERDUE.")
            )
        else:
            results.append(
                LifecycleResult(
                    bill_id, "skipped", "Bill no longer needs overdue status."
                )
            )

    _log_results("mark_overdue_bills", results)
    return results


def send_due_overdue_notifications(
    current_time: datetime | None = None,
) -> list[LifecycleResult]:
    now = current_time or timezone.now()
    minimum_notification_time = now - OVERDUE_NOTIFICATION_INTERVAL
    results: list[LifecycleResult] = []
    overdue_bill_ids = list(
        Bill.objects.filter(status=Bill.BillStatus.OVERDUE)
        .filter(
            Q(overdue_notified_at__isnull=True)
            | Q(overdue_notified_at__lte=minimum_notification_time)
        )
        .order_by("overdue_notified_at", "pk")
        .values_list("pk", flat=True)
    )

    for bill_id in overdue_bill_ids:
        try:
            with transaction.atomic():
                bill = _apply_skip_locked(
                    Bill.objects.select_related("contact", "creditor").filter(
                        pk=bill_id
                    )
                ).get()
                if bill.status != Bill.BillStatus.OVERDUE:
                    results.append(
                        LifecycleResult(
                            bill.id,
                            "skipped",
                            "Bill is no longer overdue.",
                        )
                    )
                    continue
                if (
                    bill.overdue_notified_at
                    and bill.overdue_notified_at > minimum_notification_time
                ):
                    results.append(
                        LifecycleResult(
                            bill.id,
                            "skipped",
                            "Overdue reminder is not due yet.",
                        )
                    )
                    continue

                email_sent_count = send_overdue_email(bill)
                if email_sent_count != 1:
                    results.append(
                        LifecycleResult(
                            bill.id,
                            "error",
                            f"Failed to send overdue email (returned {email_sent_count}).",
                        )
                    )
                    continue

                Bill.objects.filter(pk=bill.id).update(
                    overdue_notified_at=now,
                    overdue_notification_count=F("overdue_notification_count") + 1,
                )
                results.append(
                    LifecycleResult(
                        bill.id,
                        "processed",
                        "Overdue reminder sent.",
                    )
                )
        except Exception as exc:  # pragma: no cover - exercised in tests
            results.append(LifecycleResult(bill_id, "error", str(exc)))

    _log_results("send_due_overdue_notifications", results)
    return results


def process_bills(current_time: datetime | None = None) -> ProcessBillsSummary:
    now = current_time or timezone.now()
    generated_bills = generate_due_recurring_bills(now)
    sent_pending_bills = send_pending_bills(now)
    marked_overdue_bills = mark_overdue_bills(now)
    sent_overdue_notifications = send_due_overdue_notifications(now)
    return ProcessBillsSummary(
        generated_bills=generated_bills,
        sent_pending_bills=sent_pending_bills,
        marked_overdue_bills=marked_overdue_bills,
        sent_overdue_notifications=sent_overdue_notifications,
    )
