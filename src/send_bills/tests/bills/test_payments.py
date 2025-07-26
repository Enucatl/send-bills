import os
import io
from datetime import datetime
from decimal import Decimal

import pytest

from send_bills.bills.models import Bill
from send_bills.bills.utils import process_payments


TEST_CSV_PATH = os.path.join(os.path.dirname(__file__), "transactions.csv")


@pytest.fixture
def setup_bills_for_payments(
    contact_fixture, creditor_fixture, creditor2_fixture, tzinfo
):
    """
    Sets up all Bill instances relevant for payment processing tests.
    Returns a dictionary of these bills for easy access.
    """
    bills = {}

    bills["riccardo"] = Bill.objects.create(
        amount=Decimal("20.40"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF14YOUT20250401RICCARDO",
        status=Bill.BillStatus.OVERDUE,
        due_date=datetime(2025, 4, 1, tzinfo=tzinfo),
    )
    bills["roberto"] = Bill.objects.create(
        amount=Decimal("20.40"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF81YOUT20250401ROBERTOCA",
        status=Bill.BillStatus.SENT,
        due_date=datetime(2025, 4, 1, tzinfo=tzinfo),
    )
    bills["derek_q2"] = Bill.objects.create(
        amount=Decimal("20.40"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF96YOUT20250401DEREKCCCH",
        status=Bill.BillStatus.OVERDUE,
        due_date=datetime(2025, 4, 1, tzinfo=tzinfo),
    )
    bills["koch_q2"] = Bill.objects.create(
        amount=Decimal("20.40"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF53YOUT20250401KOCHMAXI",
        status=Bill.BillStatus.SENT,
        due_date=datetime(2025, 4, 1, tzinfo=tzinfo),
    )
    bills["moto_matteo"] = Bill.objects.create(
        amount=Decimal("75.95"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF36MOTO20250301MATTEOAB",
        status=Bill.BillStatus.OVERDUE,
        due_date=datetime(2025, 3, 1, tzinfo=tzinfo),
    )
    bills["derek_q1"] = Bill.objects.create(
        amount=Decimal("20.40"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF92YOUT20250101DEREKCCCH",
        status=Bill.BillStatus.SENT,
        due_date=datetime(2025, 1, 1, tzinfo=tzinfo),
    )
    bills["viet_derek"] = Bill.objects.create(
        amount=Decimal("1462.00"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF03VIET20250101DEREKCCCH",
        status=Bill.BillStatus.OVERDUE,
        due_date=datetime(2025, 1, 1, tzinfo=tzinfo),
    )
    bills["lookitsji"] = Bill.objects.create(
        amount=Decimal("20.40"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF39YOUT20250101LOOKITSJI",
        status=Bill.BillStatus.OVERDUE,
        due_date=datetime(2025, 1, 1, tzinfo=tzinfo),
    )
    bills["koch_q1_1"] = Bill.objects.create(
        amount=Decimal("20.40"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF84YOUT20250101KOCHMAXI",
        status=Bill.BillStatus.SENT,
        due_date=datetime(2025, 1, 1, tzinfo=tzinfo),
    )
    bills["roberto_q1"] = Bill.objects.create(
        amount=Decimal("20.40"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF77YOUT20250101ROBERTOCA",
        status=Bill.BillStatus.OVERDUE,
        due_date=datetime(2025, 1, 1, tzinfo=tzinfo),
    )
    bills["koch_q4"] = Bill.objects.create(
        amount=Decimal("18.60"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF44YOUT20241101KOCHMAXI",
        status=Bill.BillStatus.SENT,
        due_date=datetime(2024, 11, 1, tzinfo=tzinfo),
    )

    bills["different_amount"] = Bill.objects.create(
        amount=Decimal("100.00"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF14YOUT20250401RICCARDO",
        status=Bill.BillStatus.OVERDUE,
        due_date=datetime(2025, 4, 1, tzinfo=tzinfo),
    )
    bills["different_creditor"] = Bill.objects.create(
        amount=Decimal("20.40"),
        currency="CHF",
        creditor=creditor2_fixture,
        contact=contact_fixture,
        reference_number="RF14YOUT20250401RICCARDO",
        status=Bill.BillStatus.OVERDUE,
        due_date=datetime(2025, 4, 1, tzinfo=tzinfo),
    )
    bills["already_paid"] = Bill.objects.create(
        amount=Decimal("20.40"),
        currency="CHF",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF81YOUT20250401ROBERTOA",
        status=Bill.BillStatus.PAID,
        paid_at=datetime(2025, 4, 10, tzinfo=tzinfo),
        due_date=datetime(2025, 4, 1, tzinfo=tzinfo),
    )
    return bills


@pytest.fixture
def mock_csv_file():
    """Provides a file object for the transactions CSV."""
    with open(TEST_CSV_PATH, "rb") as f:
        yield io.BytesIO(f.read())


@pytest.mark.django_db
def test_process_payments_successful(setup_bills_for_payments, mock_csv_file, tzinfo):
    """
    Test that payments are processed correctly and bills are updated.
    """
    paid_count = process_payments(mock_csv_file)

    assert paid_count == 11

    for bill_key in setup_bills_for_payments:
        setup_bills_for_payments[bill_key].refresh_from_db()

    assert setup_bills_for_payments["riccardo"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["riccardo"].paid_at is not None
    assert (
        setup_bills_for_payments["riccardo"].paid_at.astimezone(tzinfo).date()
        == datetime(2025, 4, 15, tzinfo=tzinfo).date()
    )

    assert setup_bills_for_payments["roberto"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["roberto"].paid_at is not None
    assert (
        setup_bills_for_payments["roberto"].paid_at.astimezone(tzinfo).date()
        == datetime(2025, 4, 10, tzinfo=tzinfo).date()
    )

    assert setup_bills_for_payments["derek_q2"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["derek_q2"].paid_at is not None
    assert (
        setup_bills_for_payments["derek_q2"].paid_at.astimezone(tzinfo).date()
        == datetime(2025, 4, 6, tzinfo=tzinfo).date()
    )

    assert setup_bills_for_payments["koch_q2"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["koch_q2"].paid_at is not None
    assert (
        setup_bills_for_payments["koch_q2"].paid_at.astimezone(tzinfo).date()
        == datetime(2025, 4, 3, tzinfo=tzinfo).date()
    )

    assert setup_bills_for_payments["moto_matteo"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["moto_matteo"].paid_at is not None
    assert (
        setup_bills_for_payments["moto_matteo"].paid_at.astimezone(tzinfo).date()
        == datetime(2025, 3, 4, tzinfo=tzinfo).date()
    )

    assert setup_bills_for_payments["derek_q1"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["derek_q1"].paid_at is not None
    assert (
        setup_bills_for_payments["derek_q1"].paid_at.astimezone(tzinfo).date()
        == datetime(2025, 1, 23, tzinfo=tzinfo).date()
    )

    assert setup_bills_for_payments["viet_derek"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["viet_derek"].paid_at is not None
    assert (
        setup_bills_for_payments["viet_derek"].paid_at.astimezone(tzinfo).date()
        == datetime(2025, 1, 23, tzinfo=tzinfo).date()
    )

    assert setup_bills_for_payments["lookitsji"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["lookitsji"].paid_at is not None
    assert (
        setup_bills_for_payments["lookitsji"].paid_at.astimezone(tzinfo).date()
        == datetime(2025, 1, 19, tzinfo=tzinfo).date()
    )

    assert setup_bills_for_payments["koch_q1_1"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["koch_q1_1"].paid_at is not None
    assert (
        setup_bills_for_payments["koch_q1_1"].paid_at.astimezone(tzinfo).date()
        == datetime(2025, 1, 13, tzinfo=tzinfo).date()
    )

    assert setup_bills_for_payments["roberto_q1"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["roberto_q1"].paid_at is not None
    assert (
        setup_bills_for_payments["roberto_q1"].paid_at.astimezone(tzinfo).date()
        == datetime(2025, 1, 13, tzinfo=tzinfo).date()
    )

    assert setup_bills_for_payments["koch_q4"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["koch_q4"].paid_at is not None
    assert (
        setup_bills_for_payments["koch_q4"].paid_at.astimezone(tzinfo).date()
        == datetime(2024, 11, 10, tzinfo=tzinfo).date()
    )

    assert str(setup_bills_for_payments["riccardo"].paid_at.tzinfo) == "UTC"

    assert (
        setup_bills_for_payments["different_amount"].status == Bill.BillStatus.OVERDUE
    )
    assert setup_bills_for_payments["different_amount"].paid_at is None

    assert (
        setup_bills_for_payments["different_creditor"].status == Bill.BillStatus.OVERDUE
    )
    assert setup_bills_for_payments["different_creditor"].paid_at is None

    assert setup_bills_for_payments["already_paid"].status == Bill.BillStatus.PAID
    assert setup_bills_for_payments["already_paid"].paid_at is not None
    assert (
        setup_bills_for_payments["already_paid"].paid_at.astimezone(tzinfo).date()
        == datetime(2025, 4, 10, tzinfo=tzinfo).date()
    )


@pytest.mark.django_db
def test_process_payments_no_matching_bills(setup_bills_for_payments):
    """
    Test that no bills are updated if there are no matches.
    """
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
    mock_csv_file = io.BytesIO(temp_csv_content.encode("utf-8"))
    mock_csv_file.seek(0)

    bill_riccardo = setup_bills_for_payments["riccardo"]
    initial_status_riccardo = bill_riccardo.status
    initial_paid_at_riccardo = bill_riccardo.paid_at

    paid_count = process_payments(mock_csv_file)

    assert paid_count == 0
    bill_riccardo.refresh_from_db()
    assert bill_riccardo.status == initial_status_riccardo
    assert bill_riccardo.paid_at == initial_paid_at_riccardo


@pytest.mark.django_db
def test_process_payments_empty_csv():
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
    mock_csv_file = io.BytesIO(empty_csv_content.encode("utf-8"))
    mock_csv_file.seek(0)
    paid_count = process_payments(mock_csv_file)
    assert paid_count == 0


@pytest.mark.django_db
def test_process_payments_csv_without_scor_entries():
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
    mock_csv_file = io.BytesIO(no_scor_csv_content.encode("utf-8"))
    mock_csv_file.seek(0)
    paid_count = process_payments(mock_csv_file)
    assert paid_count == 0


@pytest.mark.django_db
def test_process_payments_with_different_currency(
    setup_bills_for_payments,
    mock_csv_file,
    creditor_fixture,
    contact_fixture,
    tzinfo,
):
    """
    Test that bills with different currencies are not matched.
    """
    Bill.objects.create(
        amount=Decimal("20.40"),
        currency="USD",
        creditor=creditor_fixture,
        contact=contact_fixture,
        reference_number="RF14YOUT20250401RICCARDO",
        status=Bill.BillStatus.OVERDUE,
        due_date=datetime(2025, 4, 1, tzinfo=tzinfo),
    )

    paid_count = process_payments(mock_csv_file)

    assert paid_count == 11


@pytest.mark.django_db
def test_process_payments_idempotency(setup_bills_for_payments, mock_csv_file):
    """
    Test that running the function multiple times doesn't re-update already paid bills.
    """
    paid_count_1st_run = process_payments(mock_csv_file)
    assert paid_count_1st_run == 11

    bill_riccardo = setup_bills_for_payments["riccardo"]
    bill_roberto = setup_bills_for_payments["roberto"]
    bill_riccardo.refresh_from_db()
    bill_roberto.refresh_from_db()
    assert bill_riccardo.status == Bill.BillStatus.PAID
    assert bill_roberto.status == Bill.BillStatus.PAID
    initial_riccardo_paid_at = bill_riccardo.paid_at
    initial_roberto_paid_at = bill_roberto.paid_at

    mock_csv_file.seek(0)
    paid_count_2nd_run = process_payments(mock_csv_file)
    assert paid_count_2nd_run == 0

    bill_riccardo.refresh_from_db()
    bill_roberto.refresh_from_db()
    assert bill_riccardo.status == Bill.BillStatus.PAID
    assert bill_roberto.status == Bill.BillStatus.PAID
    assert bill_riccardo.paid_at == initial_riccardo_paid_at
    assert bill_roberto.paid_at == initial_roberto_paid_at
