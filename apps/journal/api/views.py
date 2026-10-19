"""DRF viewset for DayNote, scoped to the authenticated user."""
from rest_framework import viewsets

from apps.journal.models import DayNote
from apps.journal.serializers import DayNoteSerializer


class DayNoteViewSet(viewsets.ModelViewSet):
    serializer_class = DayNoteSerializer
    queryset = DayNote.objects.none()

    def get_queryset(self):
        return DayNote.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
