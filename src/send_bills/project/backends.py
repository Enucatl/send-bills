import logging

from django.contrib.auth.backends import RemoteUserBackend
from django.contrib.auth.models import AbstractUser
from django.http import HttpRequest

logger = logging.getLogger(__name__)


class CustomRemoteUserBackend(RemoteUserBackend):
    """
    Custom authentication backend that extends Django's `RemoteUserBackend`.

    This backend automatically grants superuser and staff status to any user
    successfully authenticated via a remote user mechanism (e.g., a reverse proxy
    setting `REMOTE_USER` header). It also sets an unusable password,
    as authentication is handled externally.
    """

    def configure_user(
        self, request: HttpRequest, user: AbstractUser, created: bool = True
    ) -> AbstractUser:
        """Configures the user object after successful authentication.

        This method is called by `RemoteUserBackend.authenticate` after a user
        is either found or created. It ensures that the authenticated user
        has `is_staff` and `is_superuser` set to `True`, and an unusable
        password.

        Args:
            request: The current `HttpRequest` object.
            user: The `User` object that has just been authenticated or created.
            created: A boolean indicating whether the user object was just created.
                     Defaults to `True`.

        Returns:
            The configured `User` object.
        """
        # Call the parent method to handle basic RemoteUserBackend configuration
        super().configure_user(request, user, created=created)

        # Check if the user already has staff or superuser status.
        # If not, grant them these permissions.
        # This prevents unnecessary database writes if the user already has them.
        if not user.is_staff or not user.is_superuser:
            user.is_staff = True
            user.is_superuser = True
            # Set an unusable password since authentication is external
            user.set_unusable_password()
            user.save()
            # Log the change for auditing purposes
            logger.info(
                f"User '{user.username}' granted staff and superuser permissions "
                f"via CustomRemoteUserBackend."
            )
        return user
