from django.contrib import admin

from utils.jalali import format_jalali

from .models import Goal, Milestone


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "jalali_deadline", "status", "progress")
    list_filter = ("status",)
    search_fields = ("title", "user__username")
    list_select_related = ("user",)

    @admin.display(description="ددلاین", ordering="deadline")
    def jalali_deadline(self, obj):
        return format_jalali(obj.deadline, with_weekday=False)

    @admin.display(description="پیشرفت")
    def progress(self, obj):
        return f"{obj.progress_percent}٪"


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ("title", "goal", "user", "due_date", "is_completed")
    list_filter = ("is_completed",)
    search_fields = ("title", "goal__title", "user__username")
    list_select_related = ("goal", "user")
