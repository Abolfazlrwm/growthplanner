from django.urls import path

from . import views

app_name = "habits"

urlpatterns = [
    path("", views.HabitListView.as_view(), name="list"),
    path("new/", views.HabitCreateView.as_view(), name="create"),
    path("<int:pk>/", views.habit_detail, name="detail"),
    path("<int:pk>/edit/", views.HabitUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.HabitDeleteView.as_view(), name="delete"),
    path("<int:pk>/toggle/", views.habit_toggle_active, name="toggle"),
]
