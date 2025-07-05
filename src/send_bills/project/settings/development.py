from .base import *

# --- DEVELOPMENT-SPECIFIC SETTINGS ---

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-ep!^%_su6p8t0i79b4rc!1pe_%jd&btjlgsgry=b5$x^o773mm"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Allow all hosts and origins for local development convenience
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# Conditionally add the development-only Authelia middleware
try:
    # Find the index of the middleware it should precede
    index = MIDDLEWARE.index(
        "send_bills.project.middleware.CustomHeaderRemoteUserMiddleware"
    )
    MIDDLEWARE.insert(
        index,
        "send_bills.project.dev_authelia_middleware.DevAutheliaHeaderMiddleware",
    )
except ValueError:
    # This safeguard is in case the main middleware is renamed or removed.
    print(
        "Warning: CustomHeaderRemoteUserMiddleware not found, could not insert dev middleware."
    )
