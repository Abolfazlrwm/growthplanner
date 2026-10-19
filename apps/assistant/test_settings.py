"""Isolated settings for the assistant test suite; never points tests at managed MySQL."""
from config.settings import *  # noqa: F403

# This lets the app suite run before/after the parent has added the normal integration.
if "apps.assistant" not in INSTALLED_APPS:  # noqa: F405
    INSTALLED_APPS = [*INSTALLED_APPS, "apps.assistant"]  # noqa: F405

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}
CONN_MAX_AGE = 0
