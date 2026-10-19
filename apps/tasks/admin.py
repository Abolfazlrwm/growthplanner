from django.contrib import admin

from utils.jalali import format_jalali

from .models import SubTask, Tag, Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "jalali_date", "status", "goal")
    list_filter = ("status", "date")
    search_fields = ("title", "user__username")
    date_hierarchy = "date"
    list_select_related = ("user", "goal")

    @admin.display(description="تاریخ", ordering="date")
    def jalali_date(self, obj):
        return format_jalali(obj.date, with_weekday=False)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "created_at")
    search_fields = ("name", "user__username")
    list_select_related = ("user",)


@admin.register(SubTask)
class SubTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "task", "user", "is_completed")
    list_filter = ("is_completed",)
    search_fields = ("title", "task__title", "user__username")
    list_select_related = ("task", "user")
