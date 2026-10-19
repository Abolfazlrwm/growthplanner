"""Shared form helpers."""

# One shared class from static/css/app.css (the `.field` component); light/dark and focus
# styles live there, so widgets need no per-theme classes.
INPUT_CLASSES = "field"
LTR_FIELDS = {"username", "email"}


class StyledFormMixin:
    """Give every widget the `.field` class; keep usernames/passwords left-to-right."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = INPUT_CLASSES
            if name in LTR_FIELDS or getattr(field.widget, "input_type", None) == "password":
                field.widget.attrs["dir"] = "ltr"

    def full_clean(self):
        """Validate as usual, then flag the invalid widgets for screen readers.

        This must happen *after* validation: touching `self.errors` in __init__ would run
        validation before subclasses finish setting up their fields (e.g. querysets).
        """
        super().full_clean()
        for name in self._errors or {}:
            if name in self.fields:
                self.fields[name].widget.attrs["aria-invalid"] = "true"
