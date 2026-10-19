"""DRF viewset for Task, scoped to the authenticated user."""
from rest_framework import viewsets

from apps.tasks.models import Task
from apps.tasks.serializers import TaskSerializer


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    queryset = Task.objects.none()

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user).prefetch_related("tags", "subtasks")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
