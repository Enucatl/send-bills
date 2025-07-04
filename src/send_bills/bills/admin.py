from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import render, redirect

from send_bills.bills.models import Bill, Contact, Creditor, RecurringBill
from .forms import CsvUploadForm


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "created_at")
    search_fields = ("name", "email")


@admin.register(Creditor)
class CreditorAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "iban", "city", "country", "created_at")
    search_fields = ("name", "email", "iban")

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path("upload-csv/", self.upload_csv, name="upload_csv"),
        ]
        return my_urls + urls

    def upload_csv(self, request):
        if request.method == "POST":
            form = CsvUploadForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]

                # Check if it's a CSV file
                if not csv_file.name.endswith(".csv"):
                    messages.error(request, "This is not a CSV file")
                    return redirect(".")

                self.message_user(
                    request,
                    f"Successfully created {products_created} and updated {products_updated} products.",
                    messages.SUCCESS,
                )
                return redirect("..")

        # If GET request, render the upload form
        form = CsvUploadForm()
        context = {"form": form}
        return render(request, "admin/bills/creditor/upload_csv.html", context)


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = (
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
    list_filter = ("status", "due_date", "creditor")
    search_fields = (
        "additional_information",
        "contact__name",
        "creditor__name",
        "reference_number",
    )
    # The reference number is now auto-generated, so make it read-only
    readonly_fields = ("reference_number", "created_at", "sent_at", "paid_at")
    date_hierarchy = "billing_date"  # Use billing_date as the primary date
    ordering = ("-billing_date",)  # Order by the new primary date


@admin.register(RecurringBill)
class RecurringBillAdmin(admin.ModelAdmin):
    list_display = (
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
    list_filter = (
        "is_active",
        "frequency",
        "creditor",
        "next_billing_date",
    )
    search_fields = (
        "description_template",
        "contact__name",
        "creditor__name",
    )
    readonly_fields = ("created_at",)
    date_hierarchy = "next_billing_date"
    ordering = ("-next_billing_date",)
