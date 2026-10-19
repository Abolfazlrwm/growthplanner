"""API router (foundation for the future mobile app)."""
from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.goals.api.views import GoalViewSet
from apps.habits.api.views import HabitViewSet
from apps.journal.api.views import DayNoteViewSet
from apps.tasks.api.views import TaskViewSet

router = DefaultRouter()
router.register("goals", GoalViewSet, basename="goal")
router.register("tasks", TaskViewSet, basename="task")
router.register("habits", HabitViewSet, basename="habit")
router.register("notes", DayNoteViewSet, basename="daynote")

urlpatterns = [
    # POST {"username": ..., "password": ...} -> {"token": "..."}; send it back as
    # `Authorization: Token <token>` on every other request.
    path("token/", obtain_auth_token, name="api_token"),
    path("schema/", SpectacularAPIView.as_view(), name="api_schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api_schema"), name="api_docs"),
] + router.urls
