from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
import jinja2
import pandas as pd
import stdnum.iban
import stdnum.exceptions

from .references import cleanup_reference, generate_invoice_reference


ALLOWED_DATE_OFFSETS = [
    "BusinessDay",
    "MonthEnd",
    "MonthBegin",
    "BusinessMonthEnd",
    "BusinessMonthBegin",
    "SemiMonthEnd",
    "SemiMonthBegin",
    "Week",
    "WeekOfMonth",
    "LastWeekOfMonth",
    "QuarterEnd",
    "QuarterBegin",
    "YearEnd",
    "YearBegin",
    "Easter",
]

# Dynamically create the choices tuple for the model field.
DATE_OFFSET_CHOICES = sorted([(offset, offset) for offset in ALLOWED_DATE_OFFSETS])


def get_date_offset_instance(offset_name: str, **kwargs) -> pd.DateOffset:
    """
    Safely gets an instance of a Pandas DateOffset from its string name,
    passing any provided kwargs to its constructor.
    Raises a ValidationError for invalid names or arguments.
    """
    if offset_name not in ALLOWED_DATE_OFFSETS:
        raise ValidationError(f"Invalid DateOffset name: {offset_name}")
    try:
        offset_class = getattr(pd.tseries.offsets, offset_name)
        # Pass the kwargs to the constructor
        return offset_class(**kwargs)
    except AttributeError:
        # This case is less likely now but good to keep for safety.
        raise ValidationError(
            f"Could not find a DateOffset class named '{offset_name}'."
        )
    except TypeError as e:
        # This will catch errors like passing an invalid keyword argument (e.g., 'foo')
        # or a wrong type for an argument (e.g., n='two').
        raise ValidationError(f"Invalid arguments for '{offset_name}': {e}")


class Contact(models.Model):
    name = models.CharField(max_length=1000)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Creditor(models.Model):
    city = models.CharField(max_length=1000)
    country = models.CharField(max_length=2)
    email = models.EmailField("Creditor Email", unique=True)
    iban = models.CharField(max_length=34, unique=True)
    name = models.CharField(max_length=1000)
    pcode = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.iban:
            try:
                normalized_iban = stdnum.iban.validate(self.iban)
                self.iban = normalized_iban
            except stdnum.exceptions.ValidationError as e:
                raise ValidationError({"iban": f"Invalid IBAN: {e.message}"})
            except Exception:
                raise ValidationError({
                    "iban": "An unexpected error occurred during IBAN validation."
                })


class BaseBill(models.Model):
    """
    An abstract model that provides common fields for RecurringBill and Bill.
    """

    contact = models.ForeignKey(Contact, on_delete=models.PROTECT)
    creditor = models.ForeignKey(Creditor, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Bill for {self.contact.name}"

    class Meta:
        abstract = True


class RecurringBill(BaseBill):
    frequency = models.CharField(
        max_length=50,
        choices=DATE_OFFSET_CHOICES,
        help_text="The Pandas DateOffset to use for scheduling",
    )
    frequency_kwargs = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON object with keyword arguments for the offset (e.g., {'n': 2, 'normalize': True}).",
    )
    description_template = models.TextField(
        help_text="Jinja2 template for the bill description. e.g., 'Service for {{ billing_date.year }}'."
    )
    start_date = models.DateTimeField(default=timezone.now)
    next_billing_date = models.DateTimeField(
        db_index=True,
        blank=True,
        help_text="The next date a bill will be generated and due. Defaults to start_date.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to pause generating new bills from this schedule.",
    )

    def clean(self):
        """
        Validate model data before saving.
        Ensures that the frequency and its kwargs can create a valid DateOffset.
        """
        super().clean()

        # Creation logic: ensure next_billing_date is not before start_date
        if (
            not self.pk
            and self.next_billing_date
            and self.next_billing_date < self.start_date
        ):
            raise ValidationError({
                "next_billing_date": "next_billing_date cannot be before start_date"
            })

        # Validate that the frequency and kwargs are a valid combination
        try:
            get_date_offset_instance(self.frequency, **self.frequency_kwargs)
        except ValidationError as e:
            # Raise a more specific error for the form fields
            raise ValidationError({
                "frequency": e,
                "frequency_kwargs": f"These arguments are not valid for the '{self.frequency}' offset.",
            })

    def calculate_next_billing_date(self) -> pd.Timestamp:
        """
        Calculates the next due date based on the current next_billing_date and frequency.
        """
        offset = get_date_offset_instance(self.frequency, **self.frequency_kwargs)
        current_billing_date = pd.Timestamp(self.next_billing_date)
        return current_billing_date + offset

    def save(self, *args, **kwargs):
        if not self.pk and self.next_billing_date is None:
            self.next_billing_date = self.start_date
        self.full_clean()
        super().save(*args, **kwargs)

    def generate_bill(self) -> "Bill":
        """
        Renders the template and creates a new, unsaved Bill instance.

        Args:
            billing_date: The specific billing_date for this new bill instance.

        Returns:
            An unsaved Bill object ready for creation.
        """
        # 1. Prepare the Jinja2 environment and context
        env = jinja2.Environment()
        template = env.from_string(self.description_template)
        context = {
            "bill": self,
            "billing_date": pd.Timestamp(self.next_billing_date),
        }

        # 2. Render the description
        rendered_description = template.render(context)

        # 4. Create the Bill instance
        new_bill = Bill(
            contact=self.contact,
            creditor=self.creditor,
            amount=self.amount,
            additional_information=rendered_description,
            recurring_bill=self,
            billing_date=self.next_billing_date,
        )
        return new_bill


class Bill(BaseBill):
    """
    Represents a single, concrete invoice that has been generated.
    """

    class BillStatus(models.TextChoices):
        PENDING = "pending", "Pending Generation"
        SENT = "sent", "Sent"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"

    # Link back to the schedule that created this bill, if any.
    # on_delete=SET_NULL means if the schedule is deleted, this bill remains
    # but is no longer linked to it, preserving history.
    recurring_bill = models.ForeignKey(
        RecurringBill, on_delete=models.SET_NULL, null=True, blank=True
    )
    additional_information = models.TextField(
        help_text="Rendered description for the bill (e.g., 'YouTube Premium 2025Q2')."
    )
    reference_number = models.CharField(
        blank=True,
        db_index=True,
        editable=False,
        max_length=27,
    )
    status = models.CharField(
        max_length=100, choices=BillStatus.choices, default=BillStatus.PENDING
    )
    billing_date = models.DateTimeField(default=timezone.now)
    due_date = models.DateTimeField(
        blank=True, null=True, help_text="Date by when the bill needs to be paid."
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    def _generate_reference_number(self) -> str:
        # Use the billing_date for a consistent reference
        reference_date = pd.Timestamp(self.billing_date).strftime("%Y%m%d")

        # Use parts of the contact's email and bill info for uniqueness
        contact_part = cleanup_reference(self.contact.email)[:9]
        info_part = cleanup_reference(self.additional_information)[:4]

        # Combine them to create a unique base string
        base_reference = f"{info_part}{reference_date}{contact_part}"

        # Generate the final RF-Creditor reference
        return generate_invoice_reference(base_reference)

    def save(self, *args, **kwargs):
        # If a new bill is created without an explicit due date, set it.
        if not self.pk and self.due_date is None:
            self.due_date = self.billing_date + pd.DateOffset(months=1)

        # If the reference number hasn't been set, generate it.
        if not self.reference_number:
            self.reference_number = self._generate_reference_number()
        super().save(*args, **kwargs)
