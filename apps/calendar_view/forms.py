"""Forms used by the calendar subscription management page."""
from django import forms


class CalendarSubscriptionActionForm(forms.Form):
    """Whitelists the only state-changing operations exposed by the manager."""

    ROTATE = "rotate"
    REVOKE = "revoke"
    action = forms.ChoiceField(
        choices=((ROTATE, ROTATE), (REVOKE, REVOKE)),
        widget=forms.HiddenInput,
    )
