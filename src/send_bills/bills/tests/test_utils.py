import io
from unittest.mock import MagicMock, patch, call

from django.core.mail import EmailAttachment
from django.test import TestCase

# Adjust these imports based on your actual app name
from send_bills.bills.models import Bill, Contact, Creditor

# Import all utility functions you are testing
from send_bills.bills.utils import (
    generate_attachment,
    send_bill_email,
    generate_pdf,
)


# --- Mocks for external libraries ---


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


class BillUtilityFunctionsTests(TestCase):
    def setUp(self):
        self.creditor = Creditor.objects.create(
            name="Test Creditor AG",
            city="Zurich",
            pcode="8000",
            country="CH",
            iban="CH9300762011623852957",
            email="creditor@example.com",
        )
        self.contact = Contact.objects.create(
            name="Test Contact", email="contact@example.com"
        )
        self.bill = Bill.objects.create(
            creditor=self.creditor,
            contact=self.contact,
            amount=100.50,
            currency="CHF",
            status=Bill.BillStatus.PENDING,
        )

    # --- Tests for Utility Functions ---

    @patch("qrbill.QRBill", new=MockQRBill)
    @patch("cairosvg.svg2pdf", side_effect=mock_cairosvg_svg2pdf)
    def test_generate_pdf(self, mock_svg2pdf):
        """
        Test that generate_pdf correctly produces a PDF byte stream from a Bill object.
        """
        pdf_bytes_io = generate_pdf(self.bill)

        self.assertIsInstance(pdf_bytes_io, io.BytesIO)
        self.assertGreater(pdf_bytes_io.tell(), 0, "PDF content should not be empty")
        pdf_bytes_io.seek(0)
        self.assertEqual(pdf_bytes_io.read(), b"%PDF-1.4\n% Mock PDF content\n%%EOF")

        # Verify cairosvg.svg2pdf was called correctly
        mock_svg2pdf.assert_called_once()
        args, kwargs = mock_svg2pdf.call_args

        # IMPROVEMENT: Assert the exact byte string for more precise testing.
        self.assertEqual(kwargs["bytestring"], b"<svg>Mock SVG</svg>")
        self.assertIsInstance(kwargs["write_to"], io.BytesIO)

    def test_generate_attachment(self):
        """
        Test that generate_attachment correctly creates an EmailAttachment from a PDF byte stream.
        """
        # Using a real io.BytesIO is simpler and more realistic than a MagicMock here.
        pdf_content = b"dummy pdf content"
        pdf_io = io.BytesIO(pdf_content)

        attachment = generate_attachment(pdf_io)

        self.assertIsInstance(attachment, EmailAttachment)
        self.assertEqual(attachment.filename, "bill.pdf")
        self.assertEqual(attachment.content, pdf_content)
        self.assertEqual(attachment.mimetype, "application/pdf")

        # The function must reset the stream's position to read it from the beginning.
        # This check verifies that pdf_io.seek(0) was called.
        self.assertEqual(
            pdf_io.tell(), len(pdf_content), "Stream should be read to the end"
        )
        pdf_io.seek(0)
        self.assertEqual(
            pdf_io.read(), pdf_content, "Stream content should be unchanged"
        )

    @patch("send_bills.bills.utils.generate_pdf")
    @patch("send_bills.bills.utils.generate_attachment")
    @patch("send_bills.bills.utils.render_to_string")
    @patch("send_bills.bills.utils.EmailMessage")
    def test_send_bill_email(
        self,
        mock_EmailMessage,
        mock_render_to_string,
        mock_generate_attachment,
        mock_generate_pdf,
    ):
        """
        Test the end-to-end process of sending a bill email, mocking all external dependencies.
        """
        # --- Configure Mocks ---
        mock_pdf_io = io.BytesIO(b"mock pdf bytes")
        mock_generate_pdf.return_value = mock_pdf_io

        mock_attachment = MagicMock(spec=EmailAttachment)
        mock_attachment.filename = "mock.pdf"
        mock_attachment.content = b"mock attachment content"
        mock_attachment.mimetype = "application/pdf"
        mock_generate_attachment.return_value = mock_attachment

        mock_email_instance = mock_EmailMessage.return_value
        mock_email_instance.send.return_value = 1  # Simulate 1 email sent successfully

        mock_render_to_string.side_effect = [
            "Test Subject",
            "Test Body",
        ]

        # --- Call the function under test ---
        result = send_bill_email(self.bill)

        # --- Assertions ---
        self.assertEqual(result, 1, "Should return the result of email.send()")

        # Verify calls to our utility functions
        mock_generate_pdf.assert_called_once_with(self.bill)
        mock_generate_attachment.assert_called_once_with(
            mock_pdf_io, filename="bill.pdf"
        )

        # Verify template rendering
        expected_context = {"bill": self.bill}
        mock_render_to_string.assert_has_calls(
            [
                call("emails/bill_subject.txt", context=expected_context),
                call("emails/bill_body.txt", context=expected_context),
            ]
        )

        # Verify EmailMessage instantiation
        mock_EmailMessage.assert_called_once_with(
            subject="Test Subject",
            body="Test Body",
            from_email=self.creditor.email,
            to=[self.contact.email],
            cc=[self.creditor.email],
            attachments=[mock_attachment],
        )

        # Verify the email was sent
        mock_email_instance.send.assert_called_once_with(fail_silently=False)
