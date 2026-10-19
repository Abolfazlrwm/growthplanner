"""DRF viewset for Goal, scoped to the authenticated user."""
from rest_framework import viewsets

from apps.goals.models import Goal
from apps.goals.serializers import GoalSerializer


class GoalViewSet(viewsets.ModelViewSet):
    serializer_class = GoalSerializer
    queryset = Goal.objects.none()

    def get_queryset(self):
        return Goal.objects.filter(user=self.request.user).prefetch_related("milestones")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
