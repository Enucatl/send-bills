from django.contrib.auth.middleware import PersistentRemoteUserMiddleware


class CustomHeaderRemoteUserMiddleware(PersistentRemoteUserMiddleware):
    header = "HTTP_REMOTE_USER"
