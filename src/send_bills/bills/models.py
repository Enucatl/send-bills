from typing import Any, List, Tuple

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import SET_NULL
from django.utils import timezone
from iso3166 import countries
import jinja2
import pandas as pd
import qrbill
import stdnum.exceptions
import stdnum.iban

from .references import cleanup_reference, generate_invoice_reference


ALLOWED_DATE_OFFSETS: List[str] = [
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

ALLOWED_CURRENCIES: List[Tuple[str, str]] = sorted([
    (currency, currency) for currency in qrbill.QRBill.allowed_currencies
])
LANGUAGES: List[Tuple[str, str]] = [
    (language, language) for language in ["en", "de", "fr", "it"]
]


# Dynamically create the choices tuple for the model field.
DATE_OFFSET_CHOICES: List[Tuple[str, str]] = sorted([
    (offset, offset) for offset in ALLOWED_DATE_OFFSETS
])


def get_date_offset_instance(offset_name: str, **kwargs: Any) -> pd.DateOffset:
    """Safely gets an instance of a Pandas DateOffset from its string name.

    Args:
        offset_name: The string name of the Pandas DateOffset class (e.g., "MonthEnd").
        **kwargs: Arbitrary keyword arguments to pass to the DateOffset constructor.

    Returns:
        An instance of `pd.DateOffset`.

    Raises:
        ValidationError: If the `offset_name` is not allowed, or if the
            provided `kwargs` are invalid for the specified offset.
    """
    if offset_name not in ALLOWED_DATE_OFFSETS:
        raise ValidationError(f"Invalid DateOffset name: {offset_name}")
    try:
        offset_class = getattr(pd.tseries.offsets, offset_name)
        return offset_class(**kwargs)
    except AttributeError as e:
        # This case is less likely now but good to keep for safety.
        raise ValidationError(
            f"Could not find a DateOffset class named '{offset_name}'."
        ) from e
    except TypeError as e:
        # This will catch errors like passing an invalid keyword argument (e.g., 'foo')
        # or a wrong type for an argument (e.g., n='two').
        raise ValidationError(f"Invalid arguments for '{offset_name}': {e}") from e


class Contact(models.Model):
    """Represents a contact (debtor) to whom bills are sent."""

    name: models.CharField = models.CharField(max_length=70)
    email: models.EmailField = models.EmailField(unique=True)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        """Returns the contact's name."""
        return self.name


class Creditor(models.Model):
    """Represents the creditor (bill issuer) details."""

    name: models.CharField = models.CharField(max_length=70)
    pcode: models.CharField = models.CharField(max_length=16)
    city: models.CharField = models.CharField(max_length=35)
    country: models.CharField = models.CharField(max_length=2)
    email: models.EmailField = models.EmailField("Creditor Email", unique=True)
    iban: models.CharField = models.CharField(max_length=34, unique=True)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        """Returns the creditor's name."""
        return self.name

    def clean(self) -> None:
        """Validates the Creditor model fields.

        Performs validation for:
        - `country`: Ensures it's a valid ISO 3166-1 alpha-2 code.
        - `iban`: Validates the IBAN format and checks if its country code is
          allowed by `qrbill`.

        Raises:
            ValidationError: If any of the validations fail.
        """
        super().clean()
        if self.country:
            try:
                countries.get(self.country).alpha2
            except KeyError as e:
                raise ValidationError(
                    f"The country code {self.country} is not a valid ISO3166 code."
                ) from e
        if self.iban:
            try:
                normalized_iban = stdnum.iban.validate(self.iban)
                self.iban = normalized_iban
                if self.iban[:2] not in qrbill.bill.IBAN_ALLOWED_COUNTRIES:
                    raise ValidationError({
                        "iban": (
                            f"IBAN must start with one of the allowed country codes:"
                            f" {', '.join(qrbill.bill.IBAN_ALLOWED_COUNTRIES)}"
                        )
                    })
            except stdnum.exceptions.ValidationError as e:
                raise ValidationError({"iban": f"Invalid IBAN: {e.message}"}) from e
            except Exception as e:
                # Catch any other unexpected errors during IBAN validation
                raise ValidationError({
                    "iban": f"An unexpected error occurred during IBAN validation. {e}"
                }) from e


class BaseBill(models.Model):
    """An abstract model that provides common fields for RecurringBill and Bill."""

    contact: models.ForeignKey = models.ForeignKey(Contact, on_delete=models.PROTECT)
    creditor: models.ForeignKey = models.ForeignKey(Creditor, on_delete=models.PROTECT)
    amount: models.DecimalField = models.DecimalField(max_digits=10, decimal_places=2)
    currency: models.CharField = models.CharField(
        max_length=3, default="CHF", choices=ALLOWED_CURRENCIES
    )
    language: models.CharField = models.CharField(
        max_length=2, default="en", choices=LANGUAGES
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        """Returns a string representation of the bill."""
        return f"Bill for {self.contact.name}"

    class Meta:
        """Meta options for BaseBill."""

        abstract = True


class RecurringBill(BaseBill):
    """
    Represents a recurring bill schedule.

    This model defines the parameters for generating new bills at regular intervals.
    """

    frequency: models.CharField = models.CharField(
        max_length=50,
        choices=DATE_OFFSET_CHOICES,
        help_text="The Pandas DateOffset to use for scheduling",
    )
    frequency_kwargs: models.JSONField = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "JSON object with keyword arguments for the offset (e.g., {'n': 2, 'normalize': True})."
        ),
    )
    description_template: models.TextField = models.TextField(
        help_text="Jinja2 template for the bill description. e.g., 'Service for {{ billing_date.year }}'."
    )
    start_date: models.DateTimeField = models.DateTimeField(default=timezone.now)
    next_billing_date: models.DateTimeField = models.DateTimeField(
        db_index=True,
        blank=True,
        help_text="The next date a bill will be generated. Defaults to start_date.",
    )
    is_active: models.BooleanField = models.BooleanField(
        default=True,
        help_text="Uncheck to pause generating new bills from this schedule.",
    )

    def clean(self) -> None:
        """Validates model data before saving.

        Ensures that:
        - `next_billing_date` is not before `start_date` upon creation.
        - The `frequency` and its `frequency_kwargs` can create a valid Pandas `DateOffset`.

        Raises:
            ValidationError: If any validation fails.
        """
        super().clean()

        # Creation logic: ensure next_billing_date is not before start_date
        if (
            not self.pk  # Only applies to new instances
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
                "frequency_kwargs": (
                    f"These arguments are not valid for the '{self.frequency}' offset."
                ),
            }) from e

    def calculate_next_billing_date(self) -> pd.Timestamp:
        """Calculates the next due date based on the current `next_billing_date` and `frequency`.

        Returns:
            A `pd.Timestamp` representing the calculated next billing date.
        """
        offset = get_date_offset_instance(self.frequency, **self.frequency_kwargs)
        # Ensure next_billing_date is a timezone-aware datetime for pd.Timestamp
        current_billing_date = pd.Timestamp(self.next_billing_date)
        return current_billing_date + offset

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Overrides the default save method.

        - Sets `next_billing_date` to `start_date` if it's a new instance and
        `next_billing_date` is not explicitly set.
        - Calls `full_clean()` to run all model validators before saving.
        """
        if not self.pk and self.next_billing_date is None:
            self.next_billing_date = self.start_date
        self.full_clean()  # Ensure clean() is called before saving
        super().save(*args, **kwargs)

    def generate_bill(self) -> "Bill":
        """Renders the template and creates a new, unsaved `Bill` instance.

        The `additional_information` field of the new `Bill` instance will be
        populated by rendering the `description_template` with context.

        Returns:
            An unsaved `Bill` object ready for creation.
        """
        # 1. Prepare the Jinja2 environment and context
        env = jinja2.Environment()
        template = env.from_string(self.description_template)
        context = {
            "bill_schedule": self,  # More descriptive context variable
            "billing_date": pd.Timestamp(self.next_billing_date),
            # Add any other relevant context variables here
        }

        # 2. Render the description
        rendered_description = template.render(context)

        # 3. Create the Bill instance (not saved yet)
        new_bill = Bill(
            contact=self.contact,
            creditor=self.creditor,
            amount=self.amount,
            currency=self.currency,  # Ensure currency is passed down
            language=self.language,  # Ensure language is passed down
            additional_information=rendered_description,
            recurring_bill=self,
            billing_date=self.next_billing_date,
        )
        return new_bill


class Bill(BaseBill):
    """Represents a single, concrete invoice that has been generated."""

    class BillStatus(models.TextChoices):
        """Choices for the status of a bill."""

        PENDING = "pending", "Pending Generation"
        SENT = "sent", "Sent"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"

    recurring_bill: models.ForeignKey = models.ForeignKey(
        RecurringBill,
        on_delete=SET_NULL,
        null=True,
        blank=True,
        help_text=(
            "Link back to the schedule that created this bill. If the schedule is"
            " deleted, this bill remains but is no longer linked."
        ),
    )
    additional_information: models.TextField = models.TextField(
        help_text="Rendered description for the bill (e.g., 'YouTube Premium 2025Q2')."
    )
    reference_number: models.CharField = models.CharField(
        blank=True,
        db_index=True,
        editable=False,
        max_length=27,
        help_text="Unique RF-Creditor Reference for the bill.",
    )
    status: models.CharField = models.CharField(
        max_length=100, choices=BillStatus.choices, default=BillStatus.PENDING
    )
    billing_date: models.DateTimeField = models.DateTimeField(default=timezone.now)
    due_date: models.DateTimeField = models.DateTimeField(
        blank=True, null=True, help_text="Date by when the bill needs to be paid."
    )
    sent_at: models.DateTimeField = models.DateTimeField(null=True, blank=True)
    paid_at: models.DateTimeField = models.DateTimeField(null=True, blank=True)

    def _generate_reference_number(self) -> str:
        """Generates a unique RF-Creditor reference number for the bill.

        The reference number is based on the billing date, contact email,
        and a cleaned version of the additional information, ensuring uniqueness
        and compliance with the RF-Creditor standard.

        Returns:
            A string representing the generated RF-Creditor reference number.
        """
        # Use the billing_date for a consistent reference
        reference_date = pd.Timestamp(self.billing_date).strftime("%Y%m%d")

        # Use parts of the contact's email and bill info for uniqueness
        contact_part = cleanup_reference(self.contact.email)[:9]
        info_part = cleanup_reference(self.additional_information)[:4]

        # Combine them to create a unique base string
        base_reference = f"{info_part}{reference_date}{contact_part}"

        # Generate the final RF-Creditor reference
        return generate_invoice_reference(base_reference)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Overrides the default save method.

        - If it's a new bill and `due_date` is not set, it defaults `due_date`
          to one month after `billing_date`.
        - Generates the `reference_number` if it's not already set.
        """
        # If a new bill is created without an explicit due date, set it.
        if not self.pk and self.due_date is None:
            # Ensure billing_date is a timezone-aware datetime for pd.Timestamp
            self.due_date = pd.Timestamp(self.billing_date) + pd.DateOffset(months=1)

        # If the reference number hasn't been set, generate it.
        if not self.reference_number:
            self.reference_number = self._generate_reference_number()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        """Returns a string representation of the bill."""
        return f"Bill for {self.contact.name} {self.additional_information} ({self.status})"
