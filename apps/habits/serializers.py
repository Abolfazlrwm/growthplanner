"""DRF serializer for Habit, including the weekdays list <-> comma-string conversion."""
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import Habit


@extend_schema_field({"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 6}})
class WeekdaysListField(serializers.Field):
    """Exposes the model's comma-separated string as a JSON list of ints (0=Saturday..6=Friday)."""

    def to_representation(self, value):
        return [int(x) for x in value.split(",") if x.strip() != ""] if value else []

    def to_internal_value(self, data):
        if not isinstance(data, list):
            raise serializers.ValidationError("weekdays باید یک لیست از عددها باشد.")
        try:
            values = [int(x) for x in data]
        except (TypeError, ValueError):
            raise serializers.ValidationError("هر مقدار باید عدد صحیح باشد.")
        if any(v < 0 or v > 6 for v in values):
            raise serializers.ValidationError("هر عدد باید بین ۰ (شنبه) تا ۶ (جمعه) باشد.")
        return ",".join(str(v) for v in values)


class HabitSerializer(serializers.ModelSerializer):
    weekdays = WeekdaysListField(required=False)

    class Meta:
        model = Habit
        fields = ["id", "title", "goal", "weekdays", "starts_on", "start_time", "end_time", "priority", "tags", "active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_goal(self, goal):
        request = self.context["request"]
        if goal is not None and goal.user_id != request.user.id:
            raise serializers.ValidationError("این هدف متعلق به کاربر دیگری است.")
        return goal

    def validate(self, attrs):
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if end and (not start or end <= start):
            raise serializers.ValidationError({"end_time": "End time must be after start time."})
        return attrs

    def validate_tags(self, tags):
        if any(tag.user_id != self.context["request"].user.id for tag in tags):
            raise serializers.ValidationError("These labels do not belong to your account.")
        return tags
