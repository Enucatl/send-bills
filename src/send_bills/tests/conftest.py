from datetime import datetime, timezone

import pytest
from rest_framework.test import APIRequestFactory

from send_bills.bills.models import Creditor, Contact


@pytest.fixture(scope="session")
def tzinfo():
    """Provides a timezone object."""
    return timezone.utc


@pytest.fixture(scope="session")
def today_date():
    """Provides a fixed arbitrary date for time-sensitive tests."""
    return datetime(2023, 10, 26, tzinfo=timezone.utc)


@pytest.fixture
def request_factory():
    return APIRequestFactory()


@pytest.fixture
def creditor_fixture(db):
    """Creates a default Creditor instance for tests."""
    return Creditor.objects.create(
        name="Test Creditor AG",
        city="Zurich",
        pcode="8000",
        country="CH",
        iban="CH801503791J674321901",
        email="creditor@example.com",
    )


@pytest.fixture
def creditor2_fixture(db):
    """Creates a second Creditor instance for tests."""
    return Creditor.objects.create(
        name="Test Creditor 2",
        city="Zurich",
        pcode="8000",
        country="CH",
        iban="CH9300772011623852957",
        email="creditor2@example.com",
    )


@pytest.fixture
def contact_fixture(db):
    """Creates a default Contact instance for tests."""
    return Contact.objects.create(name="Contact A", email="contact_a@example.com")


@pytest.fixture
def contact2_fixture(db):
    """Creates a second Contact instance for tests."""
    return Contact.objects.create(name="Contact B", email="contact_b@example.com")
