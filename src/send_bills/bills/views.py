import logging

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt

from .models import Bill, RecurringBill
from .utils import send_bill_email


logger = logging.getLogger(__name__)


@csrf_exempt
def send_pending_bills_api_view(request):
    """
    API endpoint to check for and send newly created bills in 'pending' status.
    """
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Only POST requests are allowed"}, status=405
        )

    processed_bills_count = 0
    errors = []

    # Find all bills that are in 'pending' status
    pending_bills = Bill.objects.filter(status=Bill.BillStatus.PENDING)

    if not pending_bills.exists():
        logger.info("No pending bills found to send.")
        return JsonResponse(
            {
                "status": "success",
                "message": "No pending bills found to send.",
                "processed_count": 0,
            },
            status=200,
        )

    for bill in pending_bills:
        try:
            # Use a transaction to ensure that if email sending fails, the status isn't updated.
            # If the email sends, update the status to SENT.
            with transaction.atomic():
                success = send_bill_email(bill)
                if success == 1:
                    bill.status = Bill.BillStatus.SENT
                    bill.sent_at = now()
                    bill.save()
                    processed_bills_count += 1
                    logger.info(
                        f"Bill {bill.id} (Ref: {bill.reference_number}) status updated to SENT."
                    )
                else:
                    errors.append(f"Bill {bill.id} (Ref: {bill.reference_number})")
                    logger.error(f"Failed to send and update status for bill {bill.id}")
        except Exception as e:
            errors.append(
                f"Bill {bill.id} (Ref: {bill.reference_number}): Unexpected error - {e}"
            )
            logger.error(
                f"Unexpected error processing bill {bill.id}: {e}", exc_info=True
            )

    if errors:
        # Return partial success if some bills were processed but others failed.
        return JsonResponse(
            {
                "status": "partial_success",
                "message": f"Processed {processed_bills_count} bills successfully. Encountered errors for {len(errors)} bills.",
                "processed_count": processed_bills_count,
                "errors": errors,
            },
            status=200,
        )  # Keep 200, but client should check 'status' and 'errors' fields
    else:
        return JsonResponse(
            {
                "status": "success",
                "message": f"Successfully sent and updated {processed_bills_count} pending bills.",
                "processed_count": processed_bills_count,
            },
            status=200,
        )


@csrf_exempt
def generate_recurring_bills_api_view(request):
    """
    API endpoint to check all active recurring bills and generate new ones
    if their next_billing_date is in the past or present.
    """
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Only POST requests are allowed"}, status=405
        )

    generated_bills_count = 0
    errors = []
    skipped_not_due = []

    # Find all active recurring bills, ordered by next_billing_date
    active_recurring_bills = RecurringBill.objects.filter(
        is_active=True, next_billing_date__lte=now()
    ).order_by("next_billing_date")

    if not active_recurring_bills.exists():
        logger.info("No active recurring bills found to process.")
        return JsonResponse(
            {
                "status": "success",
                "message": "No active recurring bills found to process.",
                "generated_count": 0,
            },
            status=200,
        )

    for rb in active_recurring_bills:
        try:
            with transaction.atomic():
                # 1. Generate a new Bill instance
                new_bill = rb.generate_bill()
                new_bill.save()  # This will set status to PENDING and generate reference_number

                # 2. Update the recurring bill's next_billing_date
                # This calculates the next date based on the *current* next_billing_date
                rb.next_billing_date = rb.calculate_next_billing_date()
                rb.save()

                generated_bills_count += 1
                logger.info(
                    f"Generated new bill (ID: {new_bill.id}, Ref: {new_bill.reference_number}) "
                    f"for RecurringBill {rb.id}. Next billing date set to {rb.next_billing_date}."
                )
        except Exception as e:
            errors.append(
                f"RecurringBill {rb.id} (Desc: '{rb.description_template[:50]}...'): Unexpected error - {e}"
            )
            logger.error(
                f"Unexpected error processing RecurringBill {rb.id}: {e}",
                exc_info=True,
            )

    if errors:
        return JsonResponse(
            {
                "status": "partial_success",
                "message": f"Generated {generated_bills_count} bills successfully. "
                f"Encountered errors for {len(errors)} recurring bills. "
                f"Skipped {len(skipped_not_due)} recurring bills not yet due.",
                "generated_count": generated_bills_count,
                "errors": errors,
                "skipped_not_due": skipped_not_due,
            },
            status=200,
        )
    else:
        return JsonResponse(
            {
                "status": "success",
                "message": f"Successfully generated {generated_bills_count} bills from recurring schedules. "
                f"Skipped {len(skipped_not_due)} recurring bills not yet due.",
                "generated_count": generated_bills_count,
                "skipped_not_due": skipped_not_due,
            },
            status=200,
        )
