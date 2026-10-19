"""DRF serializers for the tasks API."""
from rest_framework import serializers

from .models import SubTask, Tag, Task


class TagSerializer(serializers.ModelSerializer):
    """Tags are returned with their owner; task writes use ``tag_ids`` below."""

    class Meta:
        model = Tag
        fields = ["id", "name", "user"]
        read_only_fields = ["id", "user"]


class SubTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubTask
        fields = ["id", "title", "is_completed", "position", "user", "task", "created_at"]
        read_only_fields = ["id", "user", "task", "created_at"]


class TaskSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(), many=True, source="tags", write_only=True, required=False
    )
    subtasks = SubTaskSerializer(many=True, read_only=True)

    class Meta:
        model = Task
        fields = [
            "id", "user", "title", "goal", "date", "start_time", "end_time",
            "status", "priority", "fail_reason", "tags", "tag_ids", "subtasks", "created_at",
        ]
        read_only_fields = ["id", "user", "created_at"]

    def validate_goal(self, goal):
        request = self.context.get("request")
        if goal is not None and goal.user_id != request.user.id:
            raise serializers.ValidationError("این هدف متعلق به کاربر دیگری است.")
        return goal

    def validate_tag_ids(self, tags):
        request = self.context.get("request")
        if request and any(tag.user_id != request.user.id for tag in tags):
            raise serializers.ValidationError("برچسب انتخاب‌شده متعلق به کاربر دیگری است.")
        return tags

    def validate(self, attrs):
        """Validate the merged time range so PATCH cannot hit the DB check constraint."""
        instance = self.instance
        start = attrs.get("start_time", instance.start_time if instance else None)
        end = attrs.get("end_time", instance.end_time if instance else None)
        if end is not None and start is None:
            raise serializers.ValidationError({"start_time": "برای ساعت پایان، ساعت شروع هم لازم است."})
        if start is not None and end is not None and end <= start:
            raise serializers.ValidationError({"end_time": "ساعت پایان باید بعد از ساعت شروع باشد."})
        return attrs
