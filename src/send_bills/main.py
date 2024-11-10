import io
import smtplib
from typing import List, Union

import click
import qrbill
import pandas as pd
from stdnum import iso7064
import cairosvg
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication


def cleanup_reference(text: str) -> str:
    text = text.upper()
    return "".join(char for char in text if char.isalnum())


def letter_to_number(text: str) -> str:
    def convert_letter(char: str) -> str:
        if char.isalpha():
            # Convert get base value according to table (A=10, B=11, etc.)
            return str(ord(char) - ord("A") + 10)
        elif char.isdigit():
            return char
        else:
            return ""

    return "".join(convert_letter(char) for char in text)


def generate_invoice_reference(invoice_number: str) -> str:
    clean_reference = cleanup_reference(invoice_number)
    raw_reference = f"{clean_reference}RF"
    as_number = letter_to_number(raw_reference)
    check_digits = iso7064.mod_97_10.calc_check_digits(as_number)
    return f"RF{check_digits}{clean_reference}"


def generate(reference: str) -> str:
    # Convert to uppercase and remove any whitespace
    reference = reference.upper().strip()

    # Add "RF00" prefix (00 are temporary check digits)
    rf_reference = f"RF00{reference}"

    # Convert letters to numbers (A=10, B=11, etc.)
    # RF becomes: 27 15 00 (R=27, F=15)
    numeric = ""
    for char in rf_reference:
        if char.isalpha():
            numeric += str(ord(char) - ord("A") + 10)
        else:
            numeric += char

    # Calculate modulus 97 (as per ISO 11649 standard)
    # The check digits should make the entire number modulo 97 equal to 1
    check_digits = 98 - (int(numeric) % 97)

    # Format check digits to two digits (pad with leading zero if needed)
    check_digits = f"{check_digits:02d}"

    # Return final reference with correct check digits
    return f"RF{check_digits}{reference}"


def generate_structured_reference(row: pd.Series) -> str:
    reference_date = (
        pd.tseries.offsets.MonthBegin().rollback(pd.Timestamp.now()).strftime("%Y%m%d")
    )
    sender = row["email"][:9]
    base_reference = f"{row['additional_information'][:4]}{reference_date}{sender}"
    reference = generate_invoice_reference(base_reference)
    return reference


def generate_qrbill(row: pd.Series) -> qrbill.QRBill:
    q = qrbill.QRBill(
        account=row["account"],
        creditor={
            "name": row["creditor_name"],
            "pcode": row["creditor_pcode"],
            "city": row["creditor_city"],
            "country": row["account"][:2],
        },
        amount=row["amount"],
        additional_information=row["additional_information"],
        reference_number=row["reference"],
    )
    return q


def generate_pdf(row: pd.Series) -> io.BytesIO:
    svg = io.StringIO()
    row["qrbill"].as_svg(svg)
    pdf_bytes = io.BytesIO()
    cairosvg.svg2pdf(bytestring=svg.getvalue(), write_to=pdf_bytes)
    pdf_bytes.seek(0)
    return pdf_bytes


def send_email(
    smtp_server,
    smtp_port,
    sender_email,
    sender_password,
    recipient_email,
    subject,
    body,
    cc_email: Union[str, List[str]] = None,
    attachments=None,
):
    """
    Send an email using SMTP with STARTTLS security.

    Parameters:
    - smtp_server: SMTP server address (e.g., 'smtp.gmail.com')
    - smtp_port: SMTP server port (usually 587 for STARTTLS)
    - sender_email: Sender's email address
    - sender_password: Sender's password or app password
    - recipient_email: Recipient's email address (or list of addresses)
    - subject: Email subject
    - body: Email body content
    - cc_email: CC recipient(s) email address (string or list of strings)
    - attachments: List of tuples (BytesIO object, filename) for PDF attachments

    Returns:
    - Boolean indicating success or failure
    """
    try:
        # Create the MIME object
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = (
            recipient_email
            if isinstance(recipient_email, str)
            else ", ".join(recipient_email)
        )
        # Handle CC recipients
        cc_list = []
        if cc_email:
            if isinstance(cc_email, str):
                message["Cc"] = cc_email
                cc_list = [cc_email]
            else:
                message["Cc"] = ", ".join(cc_email)
                cc_list = cc_email
        message["Subject"] = subject

        # Add body to email
        message.attach(MIMEText(body, "plain"))

        # Add attachments if any
        if attachments:
            for pdf_bytes, filename in attachments:
                try:
                    # Ensure pdf_bytes is at the start of the stream
                    if isinstance(pdf_bytes, io.BytesIO):
                        pdf_bytes.seek(0)
                        pdf_data = pdf_bytes.read()
                    else:
                        raise ValueError("Attachment must be a BytesIO object")

                    # Create the attachment
                    part = MIMEApplication(pdf_data, _subtype="pdf")
                    part.add_header(
                        "Content-Disposition", "attachment", filename=filename
                    )
                    message.attach(part)

                except Exception as e:
                    print(f"Error attaching file {filename}: {str(e)}")

        # Create SMTP session
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Enable TLS encryption
            # Login to the server
            server.login(sender_email, sender_password)

            # Send email
            text = message.as_string()
            if isinstance(recipient_email, str):
                recipients = [recipient_email]
            else:
                recipients = recipient_email
            server.sendmail(sender_email, recipients + cc_list, text)

        print("Email sent successfully!")
        return True

    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False


def send(row: pd.Series) -> bool:
    subject = f"Bill for {row['additional_information']}"
    body = f"""Hi, please find attached your QR Bill for {row['additional_information']}.
    Thanks,
    {row["creditor_name"].split()[0]}
    """
    return send_email(
        smtp_server=row["smtp_server"],
        smtp_port=row["smtp_port"],
        sender_email=row["creditor_email"],
        sender_password=row["creditor_password"],
        recipient_email=row["email"],
        cc_email=row["creditor_email"],
        subject=subject,
        body=body,
        attachments=[
            (row["pdf"], "bill.pdf"),
        ],
    )


@click.command()
@click.option("--input_file", type=click.File("r"))
def main(input_file):
    df = pd.read_csv(
        input_file,
        engine="pyarrow",
        dtype={"amount": "string", "creditor_pcode": "string"},
    )
    df["reference"] = df.apply(generate_structured_reference, axis=1)
    df["qrbill"] = df.apply(generate_qrbill, axis=1)
    df["pdf"] = df.apply(generate_pdf, axis=1)
    df["sent"] = df.apply(send, axis=1)
    print(df)


if __name__ == "__main__":
    main()
