from decimal import Decimal
import io

import pytest
from django.core.mail import EmailAttachment

from send_bills.bills.models import Bill
from send_bills.bills.utils import (
    generate_attachment,
    send_bill_email,
    generate_pdf,
)


class MockQRBill:
    # The __init__ must accept arguments passed by the real code,
    # even if the mock doesn't use them.
    def __init__(self, *args, **kwargs):
        pass

    def as_svg(self, *args, **kwargs):
        svg_file = args[0]
        svg_file.write("<svg>Mock SVG</svg>")


def mock_cairosvg_svg2pdf(bytestring, write_to):
    write_to.write(b"%PDF-1.4\n% Mock PDF content\n%%EOF")


# --- Fixtures for common setup ---


@pytest.fixture
def bill_fixture(creditor_fixture, contact_fixture):
    """Creates a Bill instance for tests."""
    return Bill.objects.create(
        creditor=creditor_fixture,
        contact=contact_fixture,
        amount=Decimal("100.50"),
        currency="CHF",
        status=Bill.BillStatus.PENDING,
    )


# --- Tests for Utility Functions ---


def test_generate_pdf(mocker, bill_fixture):
    """
    Test that generate_pdf correctly produces a PDF byte stream from a Bill object.
    """
    # Use mocker.patch for external library functions
    mocker.patch("qrbill.QRBill", new=MockQRBill)
    mock_svg2pdf = mocker.patch(
        "cairosvg.svg2pdf", side_effect=mock_cairosvg_svg2pdf
    )  # <--- Using mocker.patch

    pdf_bytes_io = generate_pdf(bill_fixture)

    assert isinstance(pdf_bytes_io, io.BytesIO)
    assert pdf_bytes_io.tell() > 0  # "PDF content should not be empty"
    pdf_bytes_io.seek(0)
    assert pdf_bytes_io.read() == b"%PDF-1.4\n% Mock PDF content\n%%EOF"

    # Verify cairosvg.svg2pdf was called correctly
    mock_svg2pdf.assert_called_once()
    args, kwargs = mock_svg2pdf.call_args

    assert kwargs["bytestring"] == b"<svg>Mock SVG</svg>"
    assert isinstance(kwargs["write_to"], io.BytesIO)


def test_generate_attachment():
    """
    Test that generate_attachment correctly creates an EmailAttachment from a PDF byte stream.
    """
    pdf_content = b"dummy pdf content"
    pdf_io = io.BytesIO(pdf_content)

    attachment = generate_attachment(pdf_io)

    assert isinstance(attachment, EmailAttachment)
    assert attachment.filename == "bill.pdf"
    assert attachment.content == pdf_content
    assert attachment.mimetype == "application/pdf"

    # The function must reset the stream's position to read it from the beginning.
    # This check verifies that pdf_io.seek(0) was called.
    assert pdf_io.tell() == len(pdf_content)  # "Stream should be read to the end"
    pdf_io.seek(0)
    assert pdf_io.read() == pdf_content  # "Stream content should be unchanged"


def test_send_bill_email(
    mocker, bill_fixture, creditor_fixture, contact_fixture
):  # <--- Added mocker
    """
    Test the end-to-end process of sending a bill email, mocking all external dependencies.
    """
    # --- Configure Mocks using mocker ---
    mock_pdf_io = io.BytesIO(b"mock pdf bytes")
    mock_generate_pdf = mocker.patch(
        "send_bills.bills.utils.generate_pdf", return_value=mock_pdf_io
    )

    mock_attachment = mocker.MagicMock(
        spec=EmailAttachment
    )  # <--- Using mocker.MagicMock
    mock_attachment.filename = "mock.pdf"
    mock_attachment.content = b"mock attachment content"
    mock_attachment.mimetype = "application/pdf"
    mock_generate_attachment = mocker.patch(
        "send_bills.bills.utils.generate_attachment", return_value=mock_attachment
    )

    mock_email_message = mocker.patch(
        "send_bills.bills.utils.EmailMessage"
    )  # <--- Using mocker.patch
    mock_email_instance = mock_email_message.return_value
    mock_email_instance.send.return_value = 1  # Simulate 1 email sent successfully

    mock_render_to_string = mocker.patch(
        "send_bills.bills.utils.render_to_string"
    )  # <--- Using mocker.patch
    mock_render_to_string.side_effect = [
        "Test Subject",
        "Test Body",
    ]

    # --- Call the function under test ---
    result = send_bill_email(bill_fixture)

    # --- Assertions ---
    assert result == 1  # "Should return the result of email.send()"

    # Verify calls to our utility functions
    mock_generate_pdf.assert_called_once_with(bill_fixture)
    mock_generate_attachment.assert_called_once_with(mock_pdf_io, filename="bill.pdf")

    # Verify template rendering
    expected_context = {"bill": bill_fixture}
    assert mock_render_to_string.call_args_list == [
        (("emails/bill_subject.txt",), {"context": expected_context}),
        (("emails/bill_body.txt",), {"context": expected_context}),
    ]

    # Verify EmailMessage instantiation
    mock_email_message.assert_called_once_with(
        subject="Test Subject",
        body="Test Body",
        from_email=creditor_fixture.email,  # Using fixture data directly
        to=[contact_fixture.email],  # Using fixture data directly
        cc=[creditor_fixture.email],  # Using fixture data directly
        attachments=[mock_attachment],
    )

    # Verify the email was sent
    mock_email_instance.send.assert_called_once_with(fail_silently=False)
