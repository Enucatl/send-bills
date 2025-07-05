import io

import cairosvg
from django.core.mail import EmailAttachment, EmailMessage
from django.core.files.base import File
from django.template.loader import render_to_string
import pandas as pd
import qrbill

from send_bills.bills.models import Bill


def generate_pdf(bill: Bill) -> io.BytesIO:
    creditor = {
        "city": bill.creditor.city,
        "country": bill.creditor.country,
        "name": bill.creditor.name,
        "pcode": bill.creditor.pcode,
    }
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


def send_overdue_email(bill: Bill) -> int:
    context = {"bill": bill}
    subject = render_to_string("emails/overdue_subject.txt", context=context).strip()
    body = render_to_string("emails/overdue_body.txt", context=context)
    pdf = generate_pdf(bill)
    attachment = generate_attachment(pdf)
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=bill.creditor.email,
        to=[bill.creditor.email],
        attachments=[attachment],
    )
    return email.send(fail_silently=False)


def send_bill_email(bill: Bill) -> int:
    context = {"bill": bill}
    subject = render_to_string("emails/bill_subject.txt", context=context).strip()
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


def process_payments(csv_file: File) -> int:
    a = pd.read_csv(
        csv_file,
        sep=";",
        header=8,
        dtype={
            "Addebito": "string",
            "Accredito": "string",
            "Importo singolo": "string",
        },
        dtype_backend="pyarrow",
    )
    b = a.ffill()
    c = b.loc[b["Descrizione1"].str.contains("SCOR:"), :].copy()
    paid_bills = 0
    if not c.empty:
        c["reference_number"] = (
            c["Descrizione1"].str.split(":").apply(lambda x: x[1]).str.replace(" ", "")
        )
        unpaid_bills = Bill.objects.select_related("creditor").filter(
            status__in=[Bill.BillStatus.SENT, Bill.BillStatus.OVERDUE]
        )
        for i, row in c.iterrows():
            paid_bills += unpaid_bills.filter(
                amount=row["Importo singolo"],
                creditor__iban=row["Descrizione2"],
                currency=row["Moneta"],
                reference_number=row["reference_number"],
            ).update(
                paid_at=pd.Timestamp(row["Data dell'operazione"], tz="Europe/Zurich"),
                status=Bill.BillStatus.PAID,
            )

    return paid_bills
