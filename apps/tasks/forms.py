"""Forms for the tasks app."""
from django import forms

from apps.core.forms import StyledFormMixin
from apps.goals.models import Goal
from utils.jalali import JALALI_WEEKDAYS, to_jalali

from .models import SubTask, Tag, Task, TaskPriority


class TaskForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "goal", "date", "start_time", "end_time", "priority"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["goal"].required = False
        self.fields["goal"].empty_label = "بدون هدف"
        self.fields["goal"].queryset = Goal.objects.filter(user=user) if user else Goal.objects.none()
        # Priority is optional for callers (API-style posts, older clients): blank means "medium".
        self.fields["priority"].required = False

    def clean_priority(self):
        return self.cleaned_data.get("priority") or TaskPriority.MEDIUM


class FailTaskForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ["fail_reason"]


class TaskDetailForm(StyledFormMixin, forms.ModelForm):
    """Full task edit form. Tags are limited to the logged-in user's labels."""

    class Meta:
        model = Task
        fields = ["title", "goal", "date", "start_time", "end_time", "status", "priority", "tags"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "tags": forms.SelectMultiple(attrs={"size": 4}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["goal"].required = False
        self.fields["goal"].queryset = Goal.objects.filter(user=user) if user else Goal.objects.none()
        self.fields["tags"].required = False
        self.fields["tags"].queryset = Tag.objects.filter(user=user) if user else Tag.objects.none()

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if end and not start:
            self.add_error("start_time", "برای ساعت پایان، ساعت شروع هم لازم است.")
        elif start and end and end <= start:
            self.add_error("end_time", "ساعت پایان باید بعد از ساعت شروع باشد.")
        return cleaned


class SubTaskForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SubTask
        fields = ["title"]
        widgets = {"title": forms.TextInput(attrs={"class": "field", "maxlength": 200})}


class SmartTaskPreviewForm(StyledFormMixin, forms.Form):
    """Editable fields shown after deterministic natural-language parsing."""

    RECURRENCE_CHOICES_FA = (("none", "بدون تکرار"), ("daily", "هر روز"), ("weekly", "هر هفته"))
    RECURRENCE_CHOICES_EN = (("none", "Does not repeat"), ("daily", "Daily"), ("weekly", "Weekly"))

    title = forms.CharField(max_length=200)
    goal = forms.ModelChoiceField(queryset=Goal.objects.none(), required=False)
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    end_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    priority = forms.ChoiceField(choices=TaskPriority.choices, initial=TaskPriority.MEDIUM)
    tag_names = forms.CharField(required=False, max_length=300)
    recurrence = forms.ChoiceField(choices=RECURRENCE_CHOICES_FA, initial="none")
    weekly_weekday = forms.TypedChoiceField(
        required=False,
        choices=[("", "—")] + [(str(i), label) for i, label in enumerate(JALALI_WEEKDAYS)],
        coerce=int,
        empty_value=None,
    )
    confirm_ambiguous = forms.BooleanField(required=False)

    def __init__(self, *args, user=None, language="fa", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["goal"].queryset = Goal.objects.filter(user=user) if user else Goal.objects.none()
        self.fields["recurrence"].choices = (
            self.RECURRENCE_CHOICES_EN if language == "en" else self.RECURRENCE_CHOICES_FA
        )
        labels = {"title": "عنوان", "goal": "هدف مرتبط", "date": "تاریخ", "start_time": "ساعت شروع", "end_time": "ساعت پایان", "priority": "اولویت", "tag_names": "برچسب‌ها (با ویرگول جدا کن)", "recurrence": "تکرار", "weekly_weekday": "روز تکرار هفتگی", "confirm_ambiguous": "تفسیر را بررسی و تأیید کردم"}
        if language == "en":
            labels = {"title":"Title", "goal":"Linked goal", "date":"Date", "start_time":"Start time", "end_time":"End time", "priority":"Priority", "tag_names":"Labels (comma separated)", "recurrence":"Repeat", "weekly_weekday":"Weekly repeat day", "confirm_ambiguous":"I reviewed the interpretation"}
        for name, label in labels.items():
            self.fields[name].label = label
        if language == "en":
            self.fields["weekly_weekday"].choices = [("", "—")] + [
                (str(i), label) for i, label in enumerate(("Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"))
            ]

    @staticmethod
    def parse_tag_names(raw: str) -> list[str]:
        values, seen = [], set()
        for name in (raw or "").replace("#", "").split(","):
            name = " ".join(name.strip().split())
            normalized = Tag.normalize(name)
            if not normalized:
                continue
            if len(name) > 40:
                raise forms.ValidationError("هر برچسب حداکثر ۴۰ نویسه است.")
            if normalized not in seen:
                values.append(name)
                seen.add(normalized)
        if len(values) > 12:
            raise forms.ValidationError("حداکثر ۱۲ برچسب برای هر تسک مجاز است.")
        return values

    def clean_tag_names(self):
        value = self.cleaned_data.get("tag_names", "")
        self.parse_tag_names(value)
        return value

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if end and not start:
            self.add_error("start_time", "برای ساعت پایان، ساعت شروع هم لازم است.")
        elif start and end and end <= start:
            self.add_error("end_time", "ساعت پایان باید بعد از ساعت شروع باشد.")
        if cleaned.get("recurrence") in ("daily", "weekly") and cleaned.get("date"):
            from django.utils import timezone
            if abs((cleaned["date"] - timezone.localdate()).days) > 366:
                self.add_error("date", "برای شروع تکرار، تاریخی در یک سال آینده یا گذشته انتخاب کن.")
        if cleaned.get("recurrence") == "weekly":
            weekday = cleaned.get("weekly_weekday")
            date = cleaned.get("date")
            if weekday is None:
                self.add_error("weekly_weekday", "برای تکرار هفتگی یک روز انتخاب کنید.")
            elif date and to_jalali(date).weekday() != weekday:
                self.add_error("date", "تاریخ رخداد نخست باید با روز هفتگی انتخاب‌شده یکی باشد.")
        return cleaned
