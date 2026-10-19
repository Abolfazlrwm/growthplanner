from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("", views.index, name="index"),
    path("chat/", views.chat, name="chat"),
    path("accept/", views.accept_draft, name="accept"),
    path("clear/", views.clear_history, name="clear"),
]
