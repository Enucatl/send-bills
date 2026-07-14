from dataclasses import dataclass

import pytest
from django.core.management import call_command

from send_bills.bills.services import LifecycleResult


@dataclass
class FakeSummary:
    generated_bills: list[LifecycleResult]
    sent_pending_bills: list[LifecycleResult]
    marked_overdue_bills: list[LifecycleResult]
    sent_overdue_notifications: list[LifecycleResult]


@pytest.mark.django_db
def test_process_bills_command_calls_service(mocker, capsys):
    mock_process_bills = mocker.patch(
        "send_bills.bills.management.commands.process_bills.process_bills",
        return_value=FakeSummary(
            [LifecycleResult(1, "processed", "ok")],
            [
                LifecycleResult(2, "processed", "ok"),
                LifecycleResult(3, "error", "failed"),
            ],
            [LifecycleResult(4, "processed", "ok")],
            [
                LifecycleResult(5, "processed", "ok"),
                LifecycleResult(6, "skipped", "not due"),
            ],
        ),
    )

    call_command("process_bills")

    mock_process_bills.assert_called_once_with()
    captured = capsys.readouterr()
    assert "generated=1" in captured.out
    assert "sent=1" in captured.out
    assert "marked_overdue=1" in captured.out
    assert "overdue_notifications=1" in captured.out
