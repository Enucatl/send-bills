import os
import io
from datetime import datetime
from decimal import Decimal

from pytz import timezone
from django.test import TestCase

from send_bills.bills.models import Bill, Creditor, Contact

from send_bills.bills.utils import process_payments

TEST_CSV_PATH = os.path.join(os.path.dirname(__file__), "transactions.csv")
TZ = timezone("Europe/Zurich")


class ProcessPaymentsTestCase(TestCase):
    """
    Test suite for the process_payments function.
    """

    @classmethod
    def setUpTestData(cls):
        # The common IBAN for all relevant transactions in the new CSV
        cls.common_iban = "CH801503791J674321901"

        # Create the creditor that matches the IBAN in the CSV
        cls.contact = Contact.objects.create(
            name="Generic Contact",
            email="1@email.com",
        )
        cls.creditor = Creditor.objects.create(
            name="Generic Creditor",
            email="1@email.com",
            iban=cls.common_iban,
        )
        cls.non_matching_creditor = Creditor.objects.create(
            name="Another Creditor",
            email="2@email.com",
            iban="CH1234567890123456789",  # Non-matching IBAN
        )

        # Create bills that should be updated based on the new transactions.csv
        # Note: CSV values are strings like '20.40', convert to Decimal for Bill model
        # reference_number values are extracted after 'SCOR:' and cleaned (spaces removed)

        # Matches 'SCOR: RF14 YOUT 2025 0401 RICC ARDO' (amount 20.40)
        cls.bill_riccardo = Bill.objects.create(
            amount=Decimal("20.40"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF14YOUT20250401RICCARDO",
            status=Bill.BillStatus.OVERDUE,
            due_date=datetime(2025, 4, 1, tzinfo=TZ),
        )
        # Matches 'SCOR: RF81 YOUT 2025 0401 ROBE RTOC A' (amount 20.40)
        cls.bill_roberto = Bill.objects.create(
            amount=Decimal("20.40"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF81YOUT20250401ROBERTOCA",
            status=Bill.BillStatus.SENT,
            due_date=datetime(2025, 4, 1, tzinfo=TZ),
        )
        # Matches 'SCOR: RF96 YOUT 2025 0401 DERE KCCC H' (amount 20.40)
        cls.bill_derek_q2 = Bill.objects.create(
            amount=Decimal("20.40"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF96YOUT20250401DEREKCCCH",
            status=Bill.BillStatus.OVERDUE,
            due_date=datetime(2025, 4, 1, tzinfo=TZ),
        )
        # Matches 'SCOR: RF53 YOUT 2025 0401 KOCH MAXI' (amount 20.40)
        cls.bill_koch_q2 = Bill.objects.create(
            amount=Decimal("20.40"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF53YOUT20250401KOCHMAXI",
            status=Bill.BillStatus.SENT,
            due_date=datetime(2025, 4, 1, tzinfo=TZ),
        )
        # Matches 'SCOR: RF36 MOTO 2025 0301 MATT EOAB' (amount 75.95)
        cls.bill_moto_matteo = Bill.objects.create(
            amount=Decimal("75.95"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF36MOTO20250301MATTEOAB",
            status=Bill.BillStatus.OVERDUE,
            due_date=datetime(2025, 3, 1, tzinfo=TZ),
        )
        # Matches 'SCOR: RF92 YOUT 2025 0101 DERE KCCC H' (amount 20.40)
        cls.bill_derek_q1 = Bill.objects.create(
            amount=Decimal("20.40"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF92YOUT20250101DEREKCCCH",
            status=Bill.BillStatus.SENT,
            due_date=datetime(2025, 1, 1, tzinfo=TZ),
        )
        # Matches 'SCOR: RF03 VIET 2025 0101 DERE KCCC H' (amount 1462.00)
        cls.bill_viet_derek = Bill.objects.create(
            amount=Decimal("1462.00"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF03VIET20250101DEREKCCCH",
            status=Bill.BillStatus.OVERDUE,
            due_date=datetime(2025, 1, 1, tzinfo=TZ),
        )
        # Matches 'SCOR: RF39 YOUT 2025 0101 LOOK ITSJ I' (amount 20.40)
        cls.bill_lookitsji = Bill.objects.create(
            amount=Decimal("20.40"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF39YOUT20250101LOOKITSJI",
            status=Bill.BillStatus.OVERDUE,
            due_date=datetime(2025, 1, 1, tzinfo=TZ),
        )
        # Matches 'SCOR: RF84 YOUT 2025 0101 KOCH MAXI' (amount 20.40)
        cls.bill_koch_q1_1 = Bill.objects.create(
            amount=Decimal("20.40"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF84YOUT20250101KOCHMAXI",
            status=Bill.BillStatus.SENT,
            due_date=datetime(2025, 1, 1, tzinfo=TZ),
        )
        # Matches 'SCOR: RF77 YOUT 2025 0101 ROBE RTOC A' (amount 20.40)
        cls.bill_roberto_q1 = Bill.objects.create(
            amount=Decimal("20.40"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF77YOUT20250101ROBERTOCA",
            status=Bill.BillStatus.OVERDUE,
            due_date=datetime(2025, 1, 1, tzinfo=TZ),
        )
        # Matches 'SCOR: RF44 YOUT 2024 1101 KOCH MAXI' (amount 18.60)
        cls.bill_koch_q4 = Bill.objects.create(
            amount=Decimal("18.60"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF44YOUT20241101KOCHMAXI",
            status=Bill.BillStatus.SENT,
            due_date=datetime(2024, 11, 1, tzinfo=TZ),
        )

        # Bill that should NOT be updated (different amount)
        cls.bill_different_amount = Bill.objects.create(
            amount=Decimal("100.00"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF14YOUT20250401RICCARDO",  # Same ref num, different amount
            status=Bill.BillStatus.OVERDUE,
            due_date=datetime(2025, 4, 1, tzinfo=TZ),
        )
        # Bill that should NOT be updated (different creditor)
        cls.bill_different_creditor = Bill.objects.create(
            amount=Decimal("20.40"),
            currency="CHF",
            creditor=cls.non_matching_creditor,  # Different creditor
            contact=cls.contact,
            reference_number="RF14YOUT20250401RICCARDO",
            status=Bill.BillStatus.OVERDUE,
            due_date=datetime(2025, 4, 1, tzinfo=TZ),
        )
        # Bill that should NOT be updated (already paid)
        cls.bill_already_paid = Bill.objects.create(
            amount=Decimal("20.40"),
            currency="CHF",
            creditor=cls.creditor,
            contact=cls.contact,
            reference_number="RF81YOUT20250401ROBERTOA",
            status=Bill.BillStatus.PAID,
            paid_at=datetime(2025, 4, 10, tzinfo=TZ),  # Already has a paid_at date
            due_date=datetime(2025, 4, 1, tzinfo=TZ),
        )

    def _get_mock_csv_file(self):
        return open(TEST_CSV_PATH, "rb")

    def test_process_payments_successful(self):
        """
        Test that payments are processed correctly and bills are updated.
        """
        mock_csv_file = self._get_mock_csv_file()
        paid_count = process_payments(mock_csv_file)

        # Expected paid count based on the number of SCOR: entries
        # that should match our setUpTestData bills
        # There are 9 SCOR: entries in the provided CSV.
        # We set up 9 matching bills that are overdue/sent.
        self.assertEqual(paid_count, 11)

        # Reload bills from DB to check their updated status
        self.bill_riccardo.refresh_from_db()
        self.bill_roberto.refresh_from_db()
        self.bill_derek_q2.refresh_from_db()
        self.bill_koch_q2.refresh_from_db()
        self.bill_moto_matteo.refresh_from_db()
        self.bill_derek_q1.refresh_from_db()
        self.bill_viet_derek.refresh_from_db()
        self.bill_lookitsji.refresh_from_db()
        self.bill_koch_q1_1.refresh_from_db()
        self.bill_roberto_q1.refresh_from_db()
        self.bill_koch_q4.refresh_from_db()

        self.bill_different_amount.refresh_from_db()
        self.bill_different_creditor.refresh_from_db()
        self.bill_already_paid.refresh_from_db()

        # Assertions for successfully paid bills
        self.assertEqual(self.bill_riccardo.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_riccardo.paid_at)
        self.assertEqual(
            self.bill_riccardo.paid_at.astimezone(TZ).date(),
            datetime(2025, 4, 16, tzinfo=TZ).date(),
        )

        self.assertEqual(self.bill_roberto.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_roberto.paid_at)
        self.assertEqual(
            self.bill_roberto.paid_at.astimezone(TZ).date(),
            datetime(2025, 4, 11, tzinfo=TZ).date(),
        )

        self.assertEqual(self.bill_derek_q2.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_derek_q2.paid_at)
        self.assertEqual(
            self.bill_derek_q2.paid_at.astimezone(TZ).date(),
            datetime(2025, 4, 7, tzinfo=TZ).date(),
        )

        self.assertEqual(self.bill_koch_q2.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_koch_q2.paid_at)
        self.assertEqual(
            self.bill_koch_q2.paid_at.astimezone(TZ).date(),
            datetime(2025, 4, 4, tzinfo=TZ).date(),
        )

        self.assertEqual(self.bill_moto_matteo.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_moto_matteo.paid_at)
        self.assertEqual(
            self.bill_moto_matteo.paid_at.astimezone(TZ).date(),
            datetime(2025, 3, 5, tzinfo=TZ).date(),
        )

        # Note: These next 3 (derek_q1, viet_derek) are grouped under the same
        # 'Data dell'operazione': 2025-01-24
        self.assertEqual(self.bill_derek_q1.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_derek_q1.paid_at)
        self.assertEqual(
            self.bill_derek_q1.paid_at.astimezone(TZ).date(),
            datetime(2025, 1, 24, tzinfo=TZ).date(),
        )

        self.assertEqual(self.bill_viet_derek.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_viet_derek.paid_at)
        self.assertEqual(
            self.bill_viet_derek.paid_at.astimezone(TZ).date(),
            datetime(2025, 1, 24, tzinfo=TZ).date(),
        )

        self.assertEqual(self.bill_lookitsji.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_lookitsji.paid_at)
        self.assertEqual(
            self.bill_lookitsji.paid_at.astimezone(TZ).date(),
            datetime(2025, 1, 20, tzinfo=TZ).date(),
        )  # This one is 2025-01-20

        self.assertEqual(self.bill_koch_q1_1.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_koch_q1_1.paid_at)
        self.assertEqual(
            self.bill_koch_q1_1.paid_at.astimezone(TZ).date(),
            datetime(2025, 1, 14, tzinfo=TZ).date(),
        )  # This one is 2025-01-14

        self.assertEqual(self.bill_roberto_q1.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_roberto_q1.paid_at)
        self.assertEqual(
            self.bill_roberto_q1.paid_at.astimezone(TZ).date(),
            datetime(2025, 1, 14, tzinfo=TZ).date(),
        )  # This one is 2025-01-14

        self.assertEqual(self.bill_koch_q4.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_koch_q4.paid_at)
        self.assertEqual(
            self.bill_koch_q4.paid_at.astimezone(TZ).date(),
            datetime(2024, 11, 11, tzinfo=TZ).date(),
        )  # This one is 2024-11-11

        # Check that timezone is correctly set for at least one of them
        self.assertEqual(str(self.bill_riccardo.paid_at.tzinfo), "UTC")

        # Assertions for bills that should NOT be updated
        self.assertEqual(self.bill_different_amount.status, Bill.BillStatus.OVERDUE)
        self.assertIsNone(self.bill_different_amount.paid_at)

        self.assertEqual(self.bill_different_creditor.status, Bill.BillStatus.OVERDUE)
        self.assertIsNone(self.bill_different_creditor.paid_at)

        # Check bill_already_paid status remains PAID and paid_at is unchanged (from initial setup)
        self.assertEqual(self.bill_already_paid.status, Bill.BillStatus.PAID)
        self.assertIsNotNone(self.bill_already_paid.paid_at)
        self.assertEqual(
            self.bill_already_paid.paid_at.astimezone(TZ).date(),
            datetime(2025, 4, 10, tzinfo=TZ).date(),
        )

    def test_process_payments_no_matching_bills(self):
        """
        Test that no bills are updated if there are no matches.
        """
        # Create a temporary CSV with SCOR entries but no matching bills in DB
        temp_csv_content = """Numero di conto:;0111 00111111.44;
IBAN:;CH80 1503 791J 6743 2190 1;
Dal:;2024-11-11;
Al:;2025-04-16;
Saldo iniziale:;;
Saldo finale:;;
Valutazione in:;CHF;
Numero di transazioni in questo periodo:;10;

Data dell'operazione;Ora dell'operazione;Data di contabilizzazione;Data di valuta;Moneta;Addebito;Accredito;Importo singolo;Saldo;N. di transazione;Descrizione1;Descrizione2;Descrizione3;Note a piè di pagina;
2025-04-16;;2025-04-16;2025-04-16;CHF;;20.40;;;2025106PH0001302;Accredito Creditor Reference;CH801503791J674321901;"Spese: Accredito referenza creditore; No di transazioni: 2025106PH0001302";;
;;;;CHF;;;20.40;;2025106PH0001302;SCOR: NOMATCHINGREF0000000000000000000000000000000000;CH801503791J674321901;"Spese: Accredito referenza creditore; No di transazioni: 9999106ZC1674589";;
"""
        mock_csv_file = io.StringIO()
        mock_csv_file.write(temp_csv_content)
        mock_csv_file.seek(0)

        # Get initial statuses of some bills that would normally be updated
        initial_status_riccardo = self.bill_riccardo.status
        initial_paid_at_riccardo = self.bill_riccardo.paid_at

        paid_count = process_payments(mock_csv_file)

        self.assertEqual(paid_count, 0)
        self.bill_riccardo.refresh_from_db()
        self.assertEqual(self.bill_riccardo.status, initial_status_riccardo)
        self.assertEqual(self.bill_riccardo.paid_at, initial_paid_at_riccardo)

    def test_process_payments_empty_csv(self):
        """
        Test that the function handles an empty CSV gracefully (headers only).
        """
        empty_csv_content = """Numero di conto:;0111 00111111.44;
IBAN:;CH80 1503 791J 6743 2190 1;
Dal:;2024-11-11;
Al:;2025-04-16;
Saldo iniziale:;;
Saldo finale:;;
Valutazione in:;CHF;
Numero di transazioni in questo periodo:;10;

Data dell'operazione;Ora dell'operazione;Data di contabilizzazione;Data di valuta;Moneta;Addebito;Accredito;Importo singolo;Saldo;N. di transazione;Descrizione1;Descrizione2;Descrizione3;Note a piè di pagina;
"""
        mock_csv_file = io.StringIO()
        mock_csv_file.write(empty_csv_content)
        mock_csv_file.seek(0)
        paid_count = process_payments(mock_csv_file)
        self.assertEqual(paid_count, 0)

    def test_process_payments_csv_without_scor_entries(self):
        """
        Test that the function handles a CSV without 'SCOR:' entries in the relevant column.
        """
        no_scor_csv_content = """Numero di conto:;0111 00111111.44;
IBAN:;CH80 1503 791J 6743 2190 1;
Dal:;2024-11-11;
Al:;2025-04-16;
Saldo iniziale:;;
Saldo finale:;;
Valutazione in:;CHF;
Numero di transazioni in questo periodo:;10;

Data dell'operazione;Ora dell'operazione;Data di contabilizzazione;Data di valuta;Moneta;Addebito;Accredito;Importo singolo;Saldo;N. di transazione;Descrizione1;Descrizione2;Descrizione3;Note a piè di pagina;
2025-04-16;;2025-04-16;2025-04-16;CHF;;20.40;;;2025106PH0001302;Accredito Creditor Reference;CH801503791J674321901;"Spese: Accredito referenza creditore; No di transazioni: 2025106PH0001302";;
2025-04-16;;2025-04-16;2025-04-16;CHF;;20.40;;;2025106PH0001302;NoSCORDescription;CH801503791J674321901;"Spese: Accredito referenza creditore; No di transazioni: 9999106ZC1674589";;
"""
        mock_csv_file = io.StringIO()
        mock_csv_file.write(no_scor_csv_content)
        mock_csv_file.seek(0)
        paid_count = process_payments(mock_csv_file)
        self.assertEqual(paid_count, 0)

    def test_process_payments_with_different_currency(self):
        """
        Test that bills with different currencies are not matched.
        """
        # Create a bill that matches everything but currency from the CSV
        Bill.objects.create(
            amount=Decimal("20.40"),
            currency="USD",  # Different currency
            creditor=self.creditor,
            contact=self.contact,
            reference_number="RF14YOUT20250401RICCARDO",
            status=Bill.BillStatus.OVERDUE,
            due_date=datetime(2025, 4, 1, tzinfo=TZ),
        )

        mock_csv_file = self._get_mock_csv_file()
        paid_count = process_payments(mock_csv_file)

        # Still expect 9 paid bills as the USD bill won't be matched by CHF entries in CSV
        self.assertEqual(paid_count, 11)
        # You could add assertions to ensure the USD bill's status is unchanged
        # but the primary test for successful payment covers the main cases.

    def test_process_payments_idempotency(self):
        """
        Test that running the function multiple times doesn't re-update already paid bills.
        """
        mock_csv_file = self._get_mock_csv_file()

        # First run, should update all 9 bills
        paid_count_1st_run = process_payments(mock_csv_file)
        self.assertEqual(paid_count_1st_run, 11)

        # Confirm bills are paid
        self.bill_riccardo.refresh_from_db()
        self.bill_roberto.refresh_from_db()
        self.assertEqual(self.bill_riccardo.status, Bill.BillStatus.PAID)
        self.assertEqual(self.bill_roberto.status, Bill.BillStatus.PAID)
        initial_riccardo_paid_at = self.bill_riccardo.paid_at
        initial_roberto_paid_at = self.bill_roberto.paid_at

        # Second run with the same data
        # The filter `status__in=[Bill.BillStatus.OVERDUE, Bill.BillStatus.SENT]`
        # should prevent already PAID bills from being selected again.
        mock_csv_file = self._get_mock_csv_file()
        paid_count_2nd_run = process_payments(mock_csv_file)
        self.assertEqual(paid_count_2nd_run, 0)  # No new bills should be paid

        # Verify statuses are still PAID and paid_at timestamps are the same
        self.bill_riccardo.refresh_from_db()
        self.bill_roberto.refresh_from_db()
        self.assertEqual(self.bill_riccardo.status, Bill.BillStatus.PAID)
        self.assertEqual(self.bill_roberto.status, Bill.BillStatus.PAID)
        self.assertEqual(self.bill_riccardo.paid_at, initial_riccardo_paid_at)
        self.assertEqual(self.bill_roberto.paid_at, initial_roberto_paid_at)
