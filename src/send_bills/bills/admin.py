from django.contrib import admin
from send_bills.bills.models import Bill, Contact, Creditor, RecurringBill


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "created_at")
    search_fields = ("name", "email")


@admin.register(Creditor)
class CreditorAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "iban", "city", "country", "created_at")
    search_fields = ("name", "email", "iban")


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = (
        "additional_information",
        "contact",
        "creditor",
        "amount",
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
    readonly_fields = ("reference_number", "created_at", "paid_at")
    date_hierarchy = "billing_date"  # Use billing_date as the primary date
    ordering = ("-billing_date",)  # Order by the new primary date


@admin.register(RecurringBill)
class RecurringBillAdmin(admin.ModelAdmin):
    list_display = (
        "description_template",
        "contact",
        "creditor",
        "amount",
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
