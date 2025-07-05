import io
from typing import Dict, Any

import cairosvg
from django.core.mail import EmailAttachment, EmailMessage
from django.core.files.base import File
from django.template.loader import render_to_string
import pandas as pd
import qrbill

from send_bills.bills.models import Bill


def generate_pdf(bill: Bill) -> io.BytesIO:
    """Generates a QR-bill PDF for a given Bill object.

    Args:
        bill: The Bill object for which to generate the QR-bill.

    Returns:
        An in-memory BytesIO object containing the PDF data.
    """
    creditor_data: Dict[str, str] = {
        "city": bill.creditor.city,
        "country": bill.creditor.country,
        "name": bill.creditor.name,
        "pcode": bill.creditor.pcode,
    }
    # Initialize QRBill with data from the Bill object
    q = qrbill.QRBill(
        account=bill.creditor.iban,
        additional_information=bill.additional_information,
        amount=bill.amount,
        creditor=creditor_data,
        currency=bill.currency,
        language=bill.language,
        reference_number=bill.reference_number,
    )

    # Generate SVG content
    svg_buffer = io.StringIO()
    q.as_svg(svg_buffer)

    # Convert SVG to PDF using cairosvg
    pdf_buffer = io.BytesIO()
    cairosvg.svg2pdf(
        bytestring=svg_buffer.getvalue().encode("utf-8"), write_to=pdf_buffer
    )
    return pdf_buffer


def generate_attachment(
    pdf_buffer: io.BytesIO, filename: str = "bill.pdf"
) -> EmailAttachment:
    """Generates a Django EmailAttachment from a PDF BytesIO object.

    Args:
        pdf_buffer: An in-memory BytesIO object containing the PDF data.
        filename: The desired filename for the attachment. Defaults to "bill.pdf".

    Returns:
        An EmailAttachment instance ready to be added to an email.
    """
    pdf_buffer.seek(0)  # Ensure the buffer's read pointer is at the beginning
    return EmailAttachment(
        filename=filename,
        content=pdf_buffer.read(),
        mimetype="application/pdf",
    )


def send_overdue_email(bill: Bill) -> int:
    """Sends an overdue bill notification email to the creditor.

    This function generates a PDF of the overdue bill and attaches it to the email.
    Note: The current implementation sends the overdue email *to the creditor*.
    Typically, overdue notices are sent to the *contact* (debtor).
    Consider reviewing the `to` field if the intention is to notify the debtor.

    Args:
        bill: The Bill object that is overdue.

    Returns:
        The number of emails sent (typically 1 on success).
    """
    context: Dict[str, Any] = {"bill": bill}
    subject: str = render_to_string(
        "emails/overdue_subject.txt", context=context
    ).strip()
    body: str = render_to_string("emails/overdue_body.txt", context=context)

    pdf_buffer = generate_pdf(bill)
    attachment = generate_attachment(pdf_buffer, filename="bill.pdf")

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=bill.creditor.email,  # Sender
        to=[
            bill.creditor.email
        ],  # Recipient (currently creditor, typically should be contact.email)
        attachments=[attachment],
    )
    return email.send(fail_silently=False)


def send_bill_email(bill: Bill) -> int:
    """Sends a bill email to the contact with the QR-bill PDF attached.

    Args:
        bill: The Bill object to be sent.

    Returns:
        The number of emails sent (typically 1 on success).
    """
    context: Dict[str, Any] = {"bill": bill}
    subject: str = render_to_string("emails/bill_subject.txt", context=context).strip()
    body: str = render_to_string("emails/bill_body.txt", context=context)

    pdf_buffer = generate_pdf(bill)
    attachment = generate_attachment(pdf_buffer, filename="bill.pdf")

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=bill.creditor.email,  # Sender
        to=[bill.contact.email],  # Primary recipient (the debtor)
        cc=[bill.creditor.email],  # CC the creditor for their records
        attachments=[attachment],
    )
    return email.send(fail_silently=False)


def process_payments(csv_file: File) -> int:
    """Processes a CSV file of payments and updates the status of corresponding bills.

    The CSV file is expected to be a financial statement export with specific column names.
    It identifies payments by reference number, amount, creditor IBAN, and currency.

    Args:
        csv_file: A Django File object representing the uploaded CSV file.

    Returns:
        The number of bills successfully marked as paid.
    """
    # Read the CSV file using pandas
    # Skip header rows if necessary (header=8 means rows 0-7 are skipped)
    # Using dtype_backend='pyarrow' for better performance and memory efficiency
    df = pd.read_csv(
        csv_file,
        sep=";",
        header=8,
        dtype={
            "Addebito": "string",
            "Accredito": "string",
            "Importo singolo": "string",  # Keep as string
        },
        dtype_backend="pyarrow",
    )

    # Fill forward NaN values, common in some bank statements where details span multiple rows
    df_filled = df.ffill()

    # Filter rows that contain "SCOR:" in 'Descrizione1', indicating a structured reference
    payments_df = df_filled.loc[
        df_filled["Descrizione1"].str.contains("SCOR:", na=False), :
    ].copy()

    paid_bills_count = 0
    if not payments_df.empty:
        # Extract the reference number by splitting the string after "SCOR:" and removing spaces
        payments_df["reference_number"] = (
            payments_df["Descrizione1"]
            .str.split(":")
            .apply(lambda x: x[1])  # Get the second part after split
            .str.replace(" ", "")
            .str.strip()  # Remove any whitespace
        )

        # Pre-fetch unpaid bills to optimize database queries
        unpaid_bills_qs = Bill.objects.select_related("creditor").filter(
            status__in=[Bill.BillStatus.SENT, Bill.BillStatus.OVERDUE]
        )

        for _, row in payments_df.iterrows():
            # Filter bills based on extracted payment details
            # Using update() directly is efficient as it avoids fetching objects individually
            updated_count = unpaid_bills_qs.filter(
                amount=row["Importo singolo"],
                creditor__iban=row["Descrizione2"],
                currency=row["Moneta"],
                reference_number=row["reference_number"],
            ).update(
                paid_at=pd.Timestamp(row["Data dell'operazione"], tz="Europe/Zurich"),
                status=Bill.BillStatus.PAID,
            )
            paid_bills_count += updated_count

    return paid_bills_count
