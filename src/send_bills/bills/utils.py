import io

import cairosvg
from django.core.mail import EmailAttachment, EmailMessage
from django.template.loader import render_to_string
import qrbill

from send_bills.bills.models import Bill


def generate_pdf(bill: Bill) -> io.BytesIO:
    creditor = qrbill.bill.StructuredAddress(
        city=bill.creditor.city,
        country=bill.creditor.country,
        name=bill.creditor.name,
        pcode=bill.creditor.pcode,
    )
    q = qrbill.QRBill(
        account=bill.creditor.iban,
        additional_information=bill.additional_information,
        amount=bill.amount,
        creditor=creditor,
        currency=bill.currency,
        language=bill.language,
        reference_number=bill.reference_number,
    )
    svg = io.StringIO()
    q.as_svg(svg)
    pdf = io.BytesIO()
    cairosvg.svg2pdf(bytestring=svg.getvalue(), write_to=pdf)
    return pdf


def generate_attachment(pdf: io.BytesIO) -> EmailAttachment:
    filename = "bill.pdf"
    pdf.seek(0)
    return EmailAttachment(
        filename=filename,
        content=pdf.read(),
        mimetype="application/pdf",
    )


def send_bill_email(bill: Bill) -> int:
    context = {"bill": bill}
    subject = render_to_string("emails/bill_subject.txt", context=context)
    body = render_to_string("emails/bill_body.txt", context=context)
    pdf = generate_pdf(bill)
    attachment = generate_attachment(pdf)
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=bill.creditor.email,
        to=[bill.contact.email],
        cc=[bill.creditor.email],
        attachments=[attachment],
    )
    return email.send(fail_silently=False)
