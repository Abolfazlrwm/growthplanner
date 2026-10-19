from django.urls import include, path

urlpatterns = [
    path("assistant/", include("apps.assistant.urls")),
]
