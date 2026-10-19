"""DRF serializer for DayNote, with a friendly duplicate-date error."""
from rest_framework import serializers

from .models import DayNote


class DayNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = DayNote
        fields = ["id", "date", "text", "mood"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        request = self.context["request"]
        date = attrs.get("date", getattr(self.instance, "date", None))
        exists = DayNote.objects.filter(user=request.user, date=date)
        if self.instance:
            exists = exists.exclude(pk=self.instance.pk)
        if exists.exists():
            raise serializers.ValidationError({"date": "برای این روز قبلاً یادداشتی ثبت شده است."})
        return attrs
