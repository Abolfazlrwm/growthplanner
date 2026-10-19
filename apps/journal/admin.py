from django.contrib import admin

from utils.jalali import format_jalali

from .models import DayNote


@admin.register(DayNote)
class DayNoteAdmin(admin.ModelAdmin):
    list_display = ("user", "jalali_date", "mood")
    list_filter = ("mood",)
    search_fields = ("text", "user__username")
    list_select_related = ("user",)

    @admin.display(description="تاریخ", ordering="date")
    def jalali_date(self, obj):
        return format_jalali(obj.date, with_weekday=False)
