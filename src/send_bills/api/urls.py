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
]
