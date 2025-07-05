from typing import Any, Tuple, List, Optional, Dict

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import path

from .forms import CsvUploadForm
from .models import Bill, Contact, Creditor, RecurringBill
from .utils import process_payments


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    """Admin configuration for the Contact model."""

    list_display: Tuple[str] = ("name", "email", "created_at")
    search_fields: Tuple[str] = ("name", "email")
    readonly_fields: Tuple[str] = ("created_at",)


@admin.register(Creditor)
class CreditorAdmin(admin.ModelAdmin):
    """Admin configuration for the Creditor model, including CSV upload for payments."""

    list_display: Tuple[str] = (
        "name",
        "email",
        "iban",
        "city",
        "country",
        "created_at",
    )
    search_fields: Tuple[str] = ("name", "email", "iban")
    readonly_fields: Tuple[str] = ("created_at",)

    def get_urls(self) -> List[Any]:
        """Extends the default admin URLs with a custom CSV upload URL.

        Returns:
            A list of URL patterns, including the custom upload_csv path.
        """
        urls = super().get_urls()
        my_urls = [
            path(
                "upload-csv/",
                self.admin_site.admin_view(self.upload_csv),
                name="upload_csv",
            ),
        ]
        return my_urls + urls

    def upload_csv(self, request: HttpRequest) -> HttpResponse:
        """Handles the CSV upload for marking payments.

        Expects a CSV file with payment data to process and mark bills as paid.

        Args:
            request: The HttpRequest object.

        Returns:
            An HttpResponse redirecting back to the Creditor list view
            with a success or error message, or rendering the upload form.
        """
        if request.method == "POST":
            form = CsvUploadForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]

                # Check if it's a CSV file based on filename extension
                if not csv_file.name.lower().endswith(".csv"):
                    self.message_user(
                        request, "This is not a CSV file.", messages.ERROR
                    )
                    return redirect(".")

                try:
                    paid_bills_count = process_payments(csv_file)
                    self.message_user(
                        request,
                        f"Successfully registered {paid_bills_count} payments.",
                        messages.SUCCESS,
                    )
                except Exception as e:
                    # Catch broad exceptions from process_payments for robust error handling
                    self.message_user(
                        request,
                        f"An error occurred during payment processing: {e}",
                        messages.ERROR,
                    )
                return redirect("..")  # Redirect back to the creditor list view

        # For GET request, render the upload form
        form = CsvUploadForm()
        context = {
            "form": form,
            "site_header": self.admin_site.site_header,
            "site_title": self.admin_site.site_title,
            "title": "Upload Payments CSV",
            "opts": self.model._meta,  # Required for admin template context
            "has_permission": self.has_add_permission(request),  # Check user permission
        }
        return render(request, "admin/bills/creditor/upload_csv.html", context)


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    """Admin configuration for the Bill model."""

    list_display: Tuple[str] = (
        "additional_information",
        "contact",
        "creditor",
        "amount",
        "currency",
        "status",
        "billing_date",
        "due_date",
        "paid_at",
        "reference_number",
    )
    list_filter: Tuple[str] = ("status", "due_date", "creditor", "currency")
    search_fields: Tuple[str] = (
        "additional_information",
        "contact__name",
        "creditor__name",
        "reference_number",
        "amount",
    )
    # The reference number is now auto-generated, so make it read-only
    readonly_fields: Tuple[str] = ("reference_number", "created_at", "sent_at")
    date_hierarchy: str = (
        "billing_date"  # Use billing_date as the primary date for drill-down
    )
    ordering: Tuple[str] = ("-billing_date",)  # Order by the new primary date
    fieldsets: Tuple[Tuple[Optional[str], Dict[str, Any]]] = (
        (None, {"fields": ("contact", "creditor", "amount", "currency", "language")}),
        (
            "Bill Details",
            {
                "fields": (
                    "additional_information",
                    "recurring_bill",
                    "reference_number",
                    "status",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "billing_date",
                    "due_date",
                    "created_at",
                    "sent_at",
                    "paid_at",
                )
            },
        ),
    )


@admin.register(RecurringBill)
class RecurringBillAdmin(admin.ModelAdmin):
    """Admin configuration for the RecurringBill model."""

    list_display: Tuple[str] = (
        "description_template",
        "contact",
        "creditor",
        "amount",
        "currency",
        "frequency",
        "is_active",
        "start_date",
        "next_billing_date",
    )
    list_filter: Tuple[str] = (
        "is_active",
        "frequency",
        "creditor",
        "next_billing_date",
        "currency",
    )
    search_fields: Tuple[str] = (
        "description_template",
        "contact__name",
        "creditor__name",
    )
    readonly_fields: Tuple[str] = ("created_at",)
    date_hierarchy: str = "next_billing_date"
    ordering: Tuple[str] = ("-next_billing_date",)
    fieldsets: Tuple[Tuple[Optional[str], Dict[str, Any]]] = (
        (
            None,
            {
                "fields": (
                    "contact",
                    "creditor",
                    "amount",
                    "currency",
                    "language",
                    "description_template",
                )
            },
        ),
        (
            "Scheduling",
            {
                "fields": (
                    "frequency",
                    "frequency_kwargs",
                    "start_date",
                    "next_billing_date",
                    "is_active",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at",)}),
    )
