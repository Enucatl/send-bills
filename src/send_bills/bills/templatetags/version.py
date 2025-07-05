import os
from django import template

register = template.Library()


@register.simple_tag
def version():
    return os.environ.get("VERSION", "unknown")
