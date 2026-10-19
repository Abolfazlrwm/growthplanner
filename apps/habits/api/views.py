"""DRF viewset for Habit, scoped to the authenticated user."""
from rest_framework import viewsets

from apps.habits.models import Habit
from apps.habits.serializers import HabitSerializer


class HabitViewSet(viewsets.ModelViewSet):
    serializer_class = HabitSerializer
    queryset = Habit.objects.none()

    def get_queryset(self):
        return Habit.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        from apps.habits.services import reconcile_future_occurrences
        habit = serializer.save()
        reconcile_future_occurrences(habit)
