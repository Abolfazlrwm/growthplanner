from django.urls import path

from . import views

app_name = "journal"

urlpatterns = [
    path("", views.note_list, name="list"),
    path("<str:date>/save/", views.save_note, name="save"),
]
