from django.urls import path
from . import views

app_name = "bills"

urlpatterns = [
    path(
        "api/send-pending-bills/",
        views.send_pending_bills_api_view,
        name="send_pending_bills_api",
    ),
]
