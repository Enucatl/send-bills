import os

from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Fetch sensitive values from environment variables.
# The application will fail to start if these are not set.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")
CSRF_TRUSTED_ORIGINS = os.environ["CSRF_TRUSTED_ORIGINS"].split(",")

# --- PRODUCTION SECURITY SETTINGS ---
# Enforce secure cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Trust the X-Forwarded-Proto header from a reverse proxy
# SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Add other security enhancements like HSTS if needed
# SECURE_HSTS_SECONDS = 31536000  # 1 year
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
