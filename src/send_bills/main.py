import io
import smtplib
from typing import List, Union, Tuple, Optional

import click
import qrbill
import pandas as pd
from stdnum import iso7064
import cairosvg
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication


def cleanup_reference(text: str) -> str:
    """Converts text to uppercase and removes all non-alphanumeric characters.

    Args:
        text: A string to be cleaned up.

    Returns:
        A string containing only uppercase alphanumeric characters from the input.

    Examples:
        >>> cleanup_reference("Hello, World!")
        'HELLOWORLD'
        >>> cleanup_reference("Test-123")
        'TEST123'
    """
    text = text.upper()
    return "".join(char for char in text if char.isalnum())


def letter_to_number(text: str) -> str:
    """Converts letters in a string to their corresponding numerical values.

    Converts letters A-Z to numbers 10-35 (A=10, B=11, etc.). Keeps existing digits
    unchanged and removes all other characters.

    Args:
        text: A string containing letters, numbers, and/or other characters.

    Returns:
        A string containing only numbers, where:
        - Letters A-Z (case-sensitive) are converted to numbers 10-35
        - Existing digits are preserved as-is
        - All other characters are removed

    Examples:
        >>> letter_to_number("ABC123")
        "101112123"
        >>> letter_to_number("XYZ")
        "333435"
        >>> letter_to_number("A1B2C3!")
        "101112123"
    """

    def convert_letter(char: str) -> str:
        """Converts a single character to its numerical representation.

        Args:
            char: A single character to convert.

        Returns:
            A string containing either:
            - A two-digit number (10-35) if the input is a letter A-Z
            - The same digit if the input is a number
            - An empty string for any other character
        """
        if char.isalpha():
            # Convert get base value according to table (A=10, B=11, etc.)
            return str(ord(char) - ord("A") + 10)
        elif char.isdigit():
            return char
        else:
            return ""

    return "".join(convert_letter(char) for char in text)


def generate_invoice_reference(invoice_number: str) -> str:
    """Generates a structured RF creditor reference from an invoice number.

    This function creates an RF creditor reference according to ISO 11649:2009 standard.
    It first cleans the invoice number, adds the RF prefix, converts letters to numbers,
    and calculates check digits using the ISO 7064 MOD 97-10 algorithm.

    Args:
        invoice_number: A string containing the original invoice number to convert.
            Can contain letters and numbers.

    Returns:
        A string containing the complete RF creditor reference in the format
        "RFxxyyyyyyy" where:
        - xx are the two check digits
        - yyyyyyy is the cleaned invoice number

    Raises:
        ValueError: If the invoice number is invalid or cannot be converted to
            a valid RF creditor reference.

    Examples:
        >>> generate_invoice_reference("539007547034")
        'RF71539007547034'
        >>> generate_invoice_reference("ABC123")
        'RF25ABC123'
    """
    clean_reference = cleanup_reference(invoice_number)
    raw_reference = f"{clean_reference}RF"
    as_number = letter_to_number(raw_reference)
    check_digits = iso7064.mod_97_10.calc_check_digits(as_number)
    return f"RF{check_digits}{clean_reference}"


def generate_structured_reference(row: pd.Series) -> str:
    """Generates a structured reference string based on row data and current date.

    Creates a structured reference by combining additional information, current date
    (rolled back to month start), and sender email, then generates an invoice reference
    from this base string.

    Args:
        row: A pandas Series containing at least 'email' and 'additional_information'
            columns. The 'email' field should be a string containing an email address,
            and 'additional_information' should be a string with at least 4 characters.

    Returns:
        A formatted reference string combining the input data according to the specified
        structure.

    Raises:
        KeyError: If required fields 'email' or 'additional_information' are missing
            from the input Series.
        IndexError: If 'additional_information' has fewer than 4 characters or 'email'
            has fewer than 9 characters.

    Example:
        >>> row = pd.Series({
        ...     'email': 'user@example.com',
        ...     'additional_information': 'INFO123'
        ... })
        >>> generate_structured_reference(row)
        'INFO20230501user@exam'  # Example output format
    """
    reference_date = (
        pd.tseries.offsets.MonthBegin().rollback(pd.Timestamp.now()).strftime("%Y%m%d")
    )
    sender = row["email"][:9]
    base_reference = f"{row['additional_information'][:4]}{reference_date}{sender}"
    reference = generate_invoice_reference(base_reference)
    return reference


def generate_qrbill(row: pd.Series) -> qrbill.QRBill:
    """Generates a QR bill object from a pandas Series containing payment information.

    This function creates a QRBill object using payment details provided in the input
    Series. It extracts creditor information, payment amount, and reference details
    from the Series to construct the QR bill.

    Args:
        row: A pandas Series containing the following required fields:
            - account: str, The creditor's account number
            - creditor_name: str, The name of the creditor
            - creditor_pcode: str, The postal code of the creditor
            - creditor_city: str, The city of the creditor
            - amount: float, The payment amount
            - additional_information: str, Additional payment information
            - reference: str, The payment reference number

    Returns:
        QRBill: A configured QRBill object containing all the payment information.

    Raises:
        KeyError: If any required field is missing from the input Series.
        ValueError: If any field contains invalid data for QR bill generation.
    """
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
    """Generates a PDF from a QR bill SVG stored in a pandas Series.

    This function converts a QR bill from SVG format to PDF format using CairoSVG.
    The SVG is first written to a string buffer, then converted to PDF and stored
    in a bytes buffer.

    Args:
        row: A pandas Series containing a 'qrbill' field that has a method 'as_svg'
            for generating SVG content.

    Returns:
        A BytesIO object containing the generated PDF data, with the buffer position
        reset to the beginning.

    Raises:
        AttributeError: If the row doesn't contain a 'qrbill' field or if the qrbill
            object doesn't have an 'as_svg' method.
        cairosvg.Error: If there's an error during SVG to PDF conversion.
    """
    svg = io.StringIO()
    row["qrbill"].as_svg(svg)
    pdf_bytes = io.BytesIO()
    cairosvg.svg2pdf(bytestring=svg.getvalue(), write_to=pdf_bytes)
    pdf_bytes.seek(0)
    return pdf_bytes


def send_email(
    smtp_server: str,
    smtp_port: int,
    sender_email: str,
    sender_password: str,
    recipient_email: Union[str, List[str]],
    subject: str,
    body: str,
    cc_email: Optional[Union[str, List[str]]] = None,
    attachments: Optional[List[Tuple[io.BytesIO, str]]] = None,
) -> bool:
    """Sends an email using SMTP with STARTTLS security.

    Args:
        smtp_server: SMTP server address (e.g., 'smtp.gmail.com')
        smtp_port: SMTP server port (usually 587 for STARTTLS)
        sender_email: Sender's email address
        sender_password: Sender's password or app password
        recipient_email: Single recipient email address or list of recipient addresses
        subject: Email subject line
        body: Plain text content of the email body
        cc_email: Optional; Single CC recipient email address or list of CC recipient addresses
        attachments: Optional; List of tuples containing (BytesIO object, filename) for PDF attachments

    Returns:
        bool: True if email was sent successfully, False if an error occurred

    Raises:
        ValueError: If an attachment is not a BytesIO object
        smtplib.SMTPException: If there are SMTP-related errors
        IOError: If there are issues reading attachment data
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
    """Sends an email with a QR bill attachment using information from a pandas Series.

    Args:
        row (pd.Series): A pandas Series containing the following fields:
            - additional_information (str): Description of the bill
            - creditor_name (str): Full name of the creditor
            - smtp_server (str): SMTP server address
            - smtp_port (int): SMTP server port
            - creditor_email (str): Creditor's email address
            - creditor_password (str): Creditor's email password
            - email (str): Recipient's email address
            - pdf (bytes): PDF content of the bill

    Returns:
        bool: True if email was sent successfully, False otherwise.

    Example:
        >>> data = pd.Series({
        ...     'additional_information': 'January Invoice',
        ...     'creditor_name': 'John Smith',
        ...     'smtp_server': 'smtp.gmail.com',
        ...     'smtp_port': 587,
        ...     'creditor_email': 'john@example.com',
        ...     'creditor_password': '****',
        ...     'email': 'customer@example.com',
        ...     'pdf': b'pdf_content'
        ... })
        >>> send(data)
        True
    """
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
