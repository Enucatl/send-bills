import logging

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import Bill
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
                    bill.sent_at = timezone.now()
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
