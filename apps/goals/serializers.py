"""DRF serializers for the goals API (foundation for the future mobile app)."""
from rest_framework import serializers

from .models import Goal, Milestone


class MilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = ["id", "title", "due_date", "is_completed", "completed_at", "position", "user", "goal", "created_at"]
        read_only_fields = ["id", "user", "goal", "created_at"]


class GoalSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    progress_percent = serializers.ReadOnlyField()
    milestones = MilestoneSerializer(many=True, read_only=True)

    class Meta:
        model = Goal
        fields = [
            "id", "user", "title", "description", "deadline", "status",
            "progress_percent", "milestones", "created_at",
        ]
        read_only_fields = ["id", "user", "created_at"]
