"""Forms for the goals app."""
from django import forms

from apps.core.forms import StyledFormMixin

from .models import Goal, Milestone


class GoalForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Goal
        fields = ["title", "description", "deadline", "status"]
        widgets = {"deadline": forms.DateInput(attrs={"type": "date"})}


class MilestoneForm(StyledFormMixin, forms.ModelForm):
    """Goal detail's compact checkpoint form; ownership is assigned in the view."""

    class Meta:
        model = Milestone
        fields = ["title", "due_date"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "field", "maxlength": 200}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }
