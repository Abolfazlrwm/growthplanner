from django.contrib import admin

from .models import Habit


@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "active", "weekdays", "goal")
    list_filter = ("active",)
    search_fields = ("title", "user__username")
    list_select_related = ("user", "goal")
