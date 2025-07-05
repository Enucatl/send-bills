from django.contrib.auth.backends import RemoteUserBackend


class CustomRemoteUserBackend(RemoteUserBackend):
    """
    Custom backend to set superuser/staff status
    """

    def configure_user(self, user, created=True):
        super().configure_user(user, created=created)
        if not user.is_staff or not user.is_superuser:
            user.is_staff = True
            user.is_superuser = True
            user.set_unusable_password()
            user.save()
        return user
