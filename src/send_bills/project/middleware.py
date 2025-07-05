from django.contrib.auth.middleware import PersistentRemoteUserMiddleware


class CustomHeaderRemoteUserMiddleware(PersistentRemoteUserMiddleware):
    """
    Custom middleware that extends Django's `PersistentRemoteUserMiddleware`.

    This middleware is designed to work with a reverse proxy (like Nginx or Apache)
    that sets a specific HTTP header containing the remote user's identifier
    after successful authentication at the proxy level.

    The `header` attribute is set to `HTTP_REMOTE_USER`, indicating that
    this middleware will look for the `REMOTE_USER` header in the HTTP request
    (Django translates `REMOTE-USER` to `HTTP_REMOTE_USER` in `request.META`).

    This middleware will:
    1. Check for the specified HTTP header.
    2. If found, attempt to authenticate a user with that username.
    3. If authentication is successful, log the user in.
    4. If the user does not exist, it can optionally create one (depending on
       the authentication backend configured, e.g., `RemoteUserBackend`).
    5. Maintain the user's session persistently (inherited from
       `PersistentRemoteUserMiddleware`).
    """

    header: str = "HTTP_REMOTE_USER"
