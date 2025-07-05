from django.contrib.auth.middleware import PersistentRemoteUserMiddleware


class CustomHeaderRemoteUserMiddleware(PersistentRemoteUserMiddleware):
    header = "HTTP_REMOTE_USER"

    def configure_user(self, user):
        if not user.is_staff or not user.is_superuser:
            user.is_staff = True
            user.is_superuser = True
            user.save()
        return user
