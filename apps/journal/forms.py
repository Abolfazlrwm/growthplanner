"""Form for the daily journal entry (text + mood), used as an HTMX-saved partial."""
from django import forms

from apps.core.forms import StyledFormMixin

from .models import DayNote


class DayNoteForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = DayNote
        fields = ["mood", "text"]
        widgets = {
            "mood": forms.RadioSelect,
            "text": forms.Textarea(attrs={"rows": 3, "placeholder": "امروز چطور گذشت؟"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Radio inputs shouldn't get the full-width text-input styling.
        self.fields["mood"].widget.attrs.pop("class", None)
