from django.urls import path
from . import views

app_name = "api"

urlpatterns = [
    path(
        "send-pending-bills/",
        views.SendPendingBillsAPIView.as_view(),
        name="send_pending_bills",
    ),
    path(
        "generate-recurring-bills/",
        views.GenerateRecurringBillsAPIView.as_view(),
        name="generate_recurring_bills",
    ),
    path(
        "mark-overdue-bills/",
        views.MarkOverdueBillsAPIView.as_view(),
        name="mark_overdue_bills",
    ),
    path(
        "notify-overdue-bills/",
        views.NotifyOverdueBillsAPIView.as_view(),
        name="notify_overdue_bills",
    ),
]
