from django.contrib.auth.middleware import PersistentRemoteUserMiddleware


class CustomHeaderRemoteUserMiddleware(PersistentRemoteUserMiddleware):
    header = "HTTP_REMOTE_USER"

    def configure_user(self, user):
        print(user)
        print(f"{user.is_staff=}")
        print(f"{user.is_superuser=}")
        if not user.is_staff or not user.is_superuser:
            user.is_staff = True
            user.is_superuser = True
            user.set_unusable_password()
            user.save()
        return user
