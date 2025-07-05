import logging

from django.db import transaction
from django.utils.timezone import now
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from send_bills.bills.models import Bill, RecurringBill
from send_bills.bills.utils import send_bill_email

logger = logging.getLogger(__name__)


class SendPendingBillsAPIView(APIView):
    """
    API endpoint to check for and send newly created bills in 'pending' status.
    Requires POST request and token authentication.
    """

    def post(self, request, format=None):
        processed_bills_count = 0
        errors = []

        pending_bills = Bill.objects.filter(status=Bill.BillStatus.PENDING)

        if not pending_bills.exists():
            logger.info("No pending bills found to send.")
            data = {
                "status": "success",
                "message": "No pending bills found to send.",
                "processed_count": 0,
            }
            return Response(data, status=status.HTTP_200_OK)

        for bill in pending_bills:
            try:
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
                        logger.error(
                            f"Failed to send and update status for bill {bill.id}"
                        )
            except Exception as e:
                errors.append(
                    f"Bill {bill.id} (Ref: {bill.reference_number}): Unexpected error - {e}"
                )
                logger.exception(f"Unexpected error processing bill {bill.id}: {e}")

        if errors:
            data = {
                "status": "partial_success",
                "message": f"Processed {processed_bills_count} bills successfully. Encountered errors for {len(errors)} bills.",
                "processed_count": processed_bills_count,
                "errors": errors,
            }
            return Response(data, status=status.HTTP_200_OK)
        else:
            data = {
                "status": "success",
                "message": f"Successfully sent and updated {processed_bills_count} pending bills.",
                "processed_count": processed_bills_count,
            }
            return Response(data, status=status.HTTP_200_OK)


class GenerateRecurringBillsAPIView(APIView):
    """
    API endpoint to check all active recurring bills and generate new ones
    if their next_billing_date is in the past or present.
    Requires POST request and token authentication.
    """

    def post(self, request, format=None):
        generated_bills_count = 0
        errors = []

        # Find all active recurring bills due for processing.
        # The original view had a 'skipped_not_due' list which was never populated.
        # It has been removed for clarity, as the query already handles skipping.
        active_recurring_bills = RecurringBill.objects.filter(
            is_active=True, next_billing_date__lte=now()
        ).order_by("next_billing_date")

        if not active_recurring_bills.exists():
            logger.info("No active recurring bills found to process.")
            data = {
                "status": "success",
                "message": "No active recurring bills found to process.",
                "generated_count": 0,
            }
            return Response(data, status=status.HTTP_200_OK)

        for rb in active_recurring_bills:
            try:
                with transaction.atomic():
                    new_bill = rb.generate_bill()
                    new_bill.save()

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
            data = {
                "status": "partial_success",
                "message": f"Generated {generated_bills_count} bills successfully. Encountered errors for {len(errors)} recurring bills.",
                "generated_count": generated_bills_count,
                "errors": errors,
            }
            return Response(data, status=status.HTTP_200_OK)
        else:
            data = {
                "status": "success",
                "message": f"Successfully generated {generated_bills_count} bills from recurring schedules.",
                "generated_count": generated_bills_count,
            }
            return Response(data, status=status.HTTP_200_OK)
