"""Form for creating/editing a Habit, including its weekday picker."""
from django import forms

from apps.core.forms import StyledFormMixin
from apps.goals.models import Goal
from utils.jalali import JALALI_WEEKDAYS

from .models import Habit

WEEKDAY_CHOICES = [(str(i), name) for i, name in enumerate(JALALI_WEEKDAYS)]


class WeekdaysField(forms.MultipleChoiceField):
    """Stores the selected weekdays as a comma-separated string on the model."""

    def prepare_value(self, value):
        if isinstance(value, str):
            return [v for v in value.split(",") if v != ""]
        return value

    def clean(self, value):
        cleaned = super().clean(value)
        return ",".join(cleaned)


class HabitForm(StyledFormMixin, forms.ModelForm):
    weekdays = WeekdaysField(
        label="روزهای تکرار",
        required=False,
        choices=WEEKDAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text="اگر هیچ روزی را انتخاب نکنی، هر روز تکرار می‌شود.",
    )

    class Meta:
        model = Habit
        fields = ["title", "goal", "weekdays", "starts_on", "start_time", "end_time", "priority", "tags", "active"]
        widgets = {
            "starts_on": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["goal"].required = False
        self.fields["goal"].empty_label = "بدون هدف"
        self.fields["goal"].queryset = Goal.objects.filter(user=user) if user else Goal.objects.none()
        from apps.tasks.models import Tag
        self.fields["tags"].queryset = Tag.objects.filter(user=user) if user else Tag.objects.none()
        self.fields["priority"].required = False
        # Checkboxes shouldn't get the full-width text-input styling.
        self.fields["weekdays"].widget.attrs.pop("class", None)
        self.fields["active"].widget.attrs.pop("class", None)

    def clean_priority(self):
        return self.cleaned_data.get("priority") or "medium"
