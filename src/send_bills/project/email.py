import ssl

from django.core.mail.backends.smtp import EmailBackend as BaseEmailBackend

from django.utils.functional import cached_property
from django.conf import settings as django_settings


class EmailBackend(BaseEmailBackend):
    @cached_property
    def ssl_context(self):
        ssl_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS)
        # set verify location:
        if (
            hasattr(django_settings, "EMAIL_CAFILE")
            and django_settings.EMAIL_CAFILE is not None
        ):
            ssl_context.load_verify_locations(cafile=django_settings.EMAIL_CAFILE)
            return ssl_context
