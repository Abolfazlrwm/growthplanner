"""Auth forms (styled through the shared `.field` class)."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from apps.core.forms import StyledFormMixin


class RegistrationForm(StyledFormMixin, UserCreationForm):
    """Sign-up with username + password (Django's validators apply)."""
    email = forms.EmailField(label="ایمیل بازیابی (اختیاری)", required=False)

    class Meta(UserCreationForm.Meta):
        fields = ("username", "email")

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if email and get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("این ایمیل قبلاً ثبت شده است.")
        return email


class LoginForm(StyledFormMixin, AuthenticationForm):
    """Login form."""


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name", "email")
        labels = {"first_name": "نام", "last_name": "نام خانوادگی", "email": "ایمیل بازیابی"}

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if email and get_user_model().objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("این ایمیل قبلاً ثبت شده است.")
        return email
