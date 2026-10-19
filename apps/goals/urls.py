from django.urls import path

from . import views

app_name = "goals"

urlpatterns = [
    path("", views.GoalListView.as_view(), name="list"),
    path("new/", views.GoalCreateView.as_view(), name="create"),
    path("<int:pk>/", views.goal_detail, name="detail"),
    path("<int:pk>/complete/", views.goal_complete, name="complete"),
    path("<int:pk>/milestones/add/", views.milestone_add, name="milestone_add"),
    path("<int:pk>/milestones/<int:milestone_pk>/toggle/", views.milestone_toggle, name="milestone_toggle"),
    path("<int:pk>/milestones/<int:milestone_pk>/delete/", views.milestone_delete, name="milestone_delete"),
    path("<int:pk>/edit/", views.GoalUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.GoalDeleteView.as_view(), name="delete"),
]
