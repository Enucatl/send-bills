#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import logging
import sys


logger = logging.getLogger(__name__)


def main() -> None:
    """Run administrative tasks for the Django project.

    This function sets the default Django settings module and then executes
    the command-line arguments using Django's `execute_from_command_line`
    function. It also includes error handling for common Django setup issues.

    Raises:
        ImportError: If Django cannot be imported, suggesting installation
            or environment activation issues.
    """
    # Set the default settings module.
    # In a production environment, this might be overridden by an environment variable
    # like DJANGO_SETTINGS_MODULE or by specific deployment configurations.
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE", "send_bills.project.settings.development"
    )

    logger.info(f"{os.environ.get('DJANGO_SETTINGS_MODULE')=}")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # Provide a user-friendly error message if Django is not found.
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # Execute the Django management command based on command-line arguments.
    # `sys.argv` is a list of strings representing the command-line arguments.
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
