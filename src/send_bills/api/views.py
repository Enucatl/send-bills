import logging
from typing import Dict, List, Optional, Union

from django.db import transaction
from django.utils.timezone import now
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from send_bills.bills.models import Bill, RecurringBill
from send_bills.bills.utils import send_bill_email, send_overdue_email

logger = logging.getLogger(__name__)


class SendPendingBillsAPIView(APIView):
    """
    API endpoint to check for and send newly created bills in 'pending' status.

    Requires POST request. This endpoint iterates through all bills with a status
    of `Bill.BillStatus.PENDING`, attempts to send an email for each, and
    updates their status to `Bill.BillStatus.SENT` upon successful dispatch.
    """

    def post(self, request: Request, format: Optional[str] = None) -> Response:
        """Handles POST requests to send pending bills.

        Args:
            request: The Django Rest Framework Request object.
            format: Optional format suffix for the response.

        Returns:
            A DRF Response indicating the outcome of the operation, including
            counts of processed bills and any errors encountered.
        """
        processed_bills_count: int = 0
        errors: List[str] = []

        # Fetch only pending bills that are not yet sent
        pending_bills = Bill.objects.filter(
            status=Bill.BillStatus.PENDING
        ).select_related("contact", "creditor")

        if not pending_bills.exists():
            logger.info("No pending bills found to send.")
            data: Dict[str, Union[str, int]] = {
                "status": "success",
                "message": "No pending bills found to send.",
                "processed_count": 0,
            }
            return Response(data, status=status.HTTP_200_OK)

        for bill in pending_bills:
            try:
                # Use a transaction for each bill to ensure atomicity.
                # If email sending or status update fails, the changes are rolled back.
                with transaction.atomic():
                    email_sent_count = send_bill_email(bill)
                    if email_sent_count == 1:
                        bill.status = Bill.BillStatus.SENT
                        bill.sent_at = now()
                        bill.save(update_fields=["status", "sent_at"])
                        processed_bills_count += 1
                        logger.info(
                            f"Bill {bill.id} (Ref: {bill.reference_number}) status updated to SENT."
                        )
                    else:
                        errors.append(
                            f"Failed to send email for Bill {bill.id} (Ref: {bill.reference_number})."
                        )
                        logger.error(
                            f"Failed to send email (returned {email_sent_count}) for bill {bill.id}"
                        )
            except Exception as e:
                errors.append(
                    f"Bill {bill.id} (Ref: {bill.reference_number}): Unexpected error - {e}"
                )
                logger.exception(f"Unexpected error processing bill {bill.id}: {e}")

        if errors:
            response_status = (
                status.HTTP_200_OK
            )  # Still 200 if some succeeded, but indicate partial success
            message = (
                f"Processed {processed_bills_count} bills successfully. "
                f"Encountered errors for {len(errors)} bills."
            )
            data = {
                "status": "partial_success",
                "message": message,
                "processed_count": processed_bills_count,
                "errors": errors,
            }
        else:
            response_status = status.HTTP_200_OK
            message = (
                f"Successfully sent and updated {processed_bills_count} pending bills."
            )
            data = {
                "status": "success",
                "message": message,
                "processed_count": processed_bills_count,
            }
        return Response(data, status=response_status)


class GenerateRecurringBillsAPIView(APIView):
    """
    API endpoint to check all active recurring bills and generate new concrete `Bill`
    instances if their `next_billing_date` is in the past or present.

    Requires POST request. This endpoint updates the `next_billing_date` of the
    `RecurringBill` after generating a new bill.
    """

    def post(self, request: Request, format: Optional[str] = None) -> Response:
        """Handles POST requests to generate bills from recurring schedules.

        Args:
            request: The Django Rest Framework Request object.
            format: Optional format suffix for the response.

        Returns:
            A DRF Response indicating the outcome, including the count of
            generated bills and any errors.
        """
        generated_bills_count: int = 0
        errors: List[str] = []

        # Find all active recurring bills due for processing.
        # Use select_related to pre-fetch related Contact and Creditor objects
        # to avoid N+1 queries during bill generation.
        active_recurring_bills = (
            RecurringBill.objects.filter(is_active=True, next_billing_date__lte=now())
            .order_by("next_billing_date")
            .select_related("contact", "creditor")
        )

        if not active_recurring_bills.exists():
            logger.info("No active recurring bills found to process.")
            data: Dict[str, Union[str, int]] = {
                "status": "success",
                "message": "No active recurring bills found to process.",
                "generated_count": 0,
            }
            return Response(data, status=status.HTTP_200_OK)

        for rb in active_recurring_bills:
            try:
                with transaction.atomic():
                    new_bill = rb.generate_bill()
                    new_bill.save()  # This also calls new_bill.clean() and sets reference number/due date

                    # Calculate and update the next billing date for the recurring schedule
                    rb.next_billing_date = rb.calculate_next_billing_date()
                    rb.save(update_fields=["next_billing_date"])

                    generated_bills_count += 1
                    logger.info(
                        f"Generated new bill (ID: {new_bill.id}, Ref: {new_bill.reference_number}) "
                        f"for RecurringBill {rb.id}. Next billing date set to {rb.next_billing_date.isoformat()}."
                    )
            except Exception as e:
                # Log the exception details for debugging
                errors.append(
                    f"RecurringBill {rb.id} (Desc: '{rb.description_template[:50]}...'): Unexpected error - {e}"
                )
                logger.exception(
                    f"Unexpected error processing RecurringBill {rb.id}: {e}"
                )

        if errors:
            response_status = status.HTTP_200_OK
            message = (
                f"Generated {generated_bills_count} bills successfully. "
                f"Encountered errors for {len(errors)} recurring bills."
            )
            data = {
                "status": "partial_success",
                "message": message,
                "generated_count": generated_bills_count,
                "errors": errors,
            }
        else:
            response_status = status.HTTP_200_OK
            message = f"Successfully generated {generated_bills_count} bills from recurring schedules."
            data = {
                "status": "success",
                "message": message,
                "generated_count": generated_bills_count,
            }
        return Response(data, status=response_status)


class MarkOverdueBillsAPIView(APIView):
    """
    API endpoint to check and update the status of bills that are overdue.

    Requires POST request. A bill is considered overdue if its `due_date` is
    less than or equal to the current time, and its status is not already
    `Bill.BillStatus.OVERDUE`.
    """

    def post(self, request: Request, format: Optional[str] = None) -> Response:
        """Handles POST requests to mark bills as overdue.

        Args:
            request: The Django Rest Framework Request object.
            format: Optional format suffix for the response.

        Returns:
            A DRF Response indicating the number of bills updated.
        """
        # Atomically update all bills that meet the overdue criteria
        updated_count: int = (
            Bill.objects.filter(due_date__lte=now())
            .exclude(status__in=[Bill.BillStatus.OVERDUE, Bill.BillStatus.PAID])
            .update(status=Bill.BillStatus.OVERDUE)
        )
        logger.info(f"Marked {updated_count} bills as overdue.")

        data: Dict[str, Union[str, int]] = {
            "status": "success",
            "message": "Checked and updated overdue bills.",
            "updated_count": updated_count,
        }
        return Response(data, status=status.HTTP_200_OK)


class NotifyOverdueBillsAPIView(APIView):
    """
    API endpoint to send notifications for overdue bills.

    Requires POST request. This endpoint iterates through all bills currently
    in `Bill.BillStatus.OVERDUE` status and attempts to send an overdue
    notification email for each.
    """

    def post(self, request: Request, format: Optional[str] = None) -> Response:
        """Handles POST requests to send overdue bill notifications.

        Args:
            request: The Django Rest Framework Request object.
            format: Optional format suffix for the response.

        Returns:
            A DRF Response indicating the outcome, including the total
            notifications sent and any errors.
        """
        total_sent_notifications: int = 0
        errors: List[str] = []

        # Fetch overdue bills, pre-fetching related contact and creditor data
        overdue_bills = Bill.objects.select_related("creditor", "contact").filter(
            status=Bill.BillStatus.OVERDUE
        )

        if not overdue_bills.exists():
            logger.info("No overdue bills found to notify.")
            data: Dict[str, Union[str, int]] = {
                "status": "success",
                "message": "No overdue bills found to notify.",
                "notifications": 0,
                "errors": errors,
            }
            return Response(data, status=status.HTTP_200_OK)

        # Use .iterator() for potentially large querysets to reduce memory usage
        for bill in overdue_bills.iterator():
            try:
                # Use a transaction for each notification attempt
                with transaction.atomic():
                    email_sent_count = send_overdue_email(bill)
                    if email_sent_count == 1:
                        total_sent_notifications += 1
                        logger.info(
                            f"Sent overdue notification for Bill {bill.id} (Ref: {bill.reference_number})."
                        )
                    else:
                        errors.append(
                            f"Failed to send notification for Bill {bill.id} (Ref: {bill.reference_number})."
                        )
                        logger.error(
                            f"Failed to send overdue email (returned {email_sent_count}) for bill {bill.id}"
                        )
            except Exception as e:
                errors.append(
                    f"Bill {bill.id} (Ref: {bill.reference_number}): Unexpected error sending overdue notification - {e}"
                )
                logger.exception(
                    f"Unexpected error sending overdue notification for bill {bill.id}: {e}"
                )

        if errors:
            response_status = status.HTTP_200_OK
            message = (
                f"Sent {total_sent_notifications} overdue notifications successfully. "
                f"Encountered errors for {len(errors)} bills."
            )
            data = {
                "status": "partial_success",
                "message": message,
                "notifications": total_sent_notifications,
                "errors": errors,
            }
        else:
            response_status = status.HTTP_200_OK
            message = f"Successfully sent {total_sent_notifications} overdue bill notifications."
            data = {
                "status": "success",
                "message": message,
                "notifications": total_sent_notifications,
                "errors": errors,
            }
        return Response(data, status=response_status)
