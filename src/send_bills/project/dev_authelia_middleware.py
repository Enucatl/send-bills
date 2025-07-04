from django.conf import settings
from django.contrib.auth.models import User


class DevAutheliaHeaderMiddleware:
    """
    Middleware to simulate Authelia headers during local development (DEBUG=True).
    This allows testing authentication flows without running Authelia locally.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEBUG and not request.user.is_authenticated:
            dev_username = "devuser"  # Your test username
            dev_email = "devuser@example.com"  # Your test email

            request.META["HTTP_REMOTE_USER"] = dev_username
            request.META["HTTP_REMOTE_EMAIL"] = dev_email
            try:
                user = User.objects.get(username=dev_username)
                if not user.is_staff or not user.is_superuser:
                    user.is_staff = True
                    user.is_superuser = True
                    user.save()
            except User.DoesNotExist:
                # If the user doesn't exist, RemoteUserBackend will create it.
                # However, RemoteUserBackend won't set is_staff/is_superuser automatically.
                # If you want it created with these permissions automatically, you'd need
                # a custom RemoteUserBackend that overrides configure_user.
                # For this simple middleware, we rely on RemoteUserBackend to create,
                # and then if it's already created, we ensure permissions.
                user, created = User.objects.get_or_create(
                    username=dev_username,
                    defaults={
                        "email": dev_email,
                        "is_staff": True,
                        "is_superuser": True,
                    },
                )
                if created:
                    # Set an unusable password for externally managed users
                    user.set_unusable_password()
                    user.save()

        response = self.get_response(request)
        return response
