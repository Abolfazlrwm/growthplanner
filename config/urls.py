"""Root URL configuration."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("goals/", include("apps.goals.urls")),
    path("tasks/", include("apps.tasks.urls")),
    path("habits/", include("apps.habits.urls")),
    path("journal/", include("apps.journal.urls")),
    path("calendar/", include("apps.calendar_view.urls")),
    path("assistant/", include("apps.assistant.urls")),
    path("api/", include("config.api_urls")),
    path("", include("apps.core.urls")),
]
