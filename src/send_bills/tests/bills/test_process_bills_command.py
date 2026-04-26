from dataclasses import dataclass

import pytest
from django.core.management import call_command


@dataclass
class FakeSummary:
    generated_bills: list[int]
    sent_pending_bills: list[int]
    marked_overdue_bills: list[int]
    sent_overdue_notifications: list[int]


@pytest.mark.django_db
def test_process_bills_command_calls_service(mocker, capsys):
    mock_process_bills = mocker.patch(
        "send_bills.bills.management.commands.process_bills.process_bills",
        return_value=FakeSummary([1], [2], [3], [4]),
    )

    call_command("process_bills")

    mock_process_bills.assert_called_once_with()
    captured = capsys.readouterr()
    assert "generated=1" in captured.out
    assert "sent=1" in captured.out
    assert "marked_overdue=1" in captured.out
    assert "overdue_notifications=1" in captured.out
