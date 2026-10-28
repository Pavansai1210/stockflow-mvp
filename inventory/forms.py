from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Organization, Product, Profile


class SignupForm(forms.Form):
    org_name = forms.CharField(label="Organization name", min_length=2, max_length=80)
    email = forms.EmailField(max_length=150)
    password = forms.CharField(
        widget=forms.PasswordInput, help_text="At least 8 characters."
    )
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username__iexact=email).exists():
            raise ValidationError("An account with this email already exists. Log in instead.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password:
            if password != cleaned.get("confirm_password"):
                self.add_error("confirm_password", "Passwords do not match.")
            try:
                validate_password(password)
            except ValidationError as exc:
                self.add_error("password", exc)
        return cleaned

    @transaction.atomic
    def save(self):
        """Create the organization, the user and their link in one transaction."""
        data = self.cleaned_data
        org = Organization.objects.create(name=data["org_name"])
        user = User.objects.create_user(
            username=data["email"], email=data["email"], password=data["password"]
        )
        Profile.objects.create(user=user, organization=org)
        return user


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        password = cleaned.get("password")
        if email and password:
            self.user = authenticate(self.request, username=email.strip().lower(), password=password)
            if self.user is None:
                raise ValidationError("Email or password is incorrect.")
        return cleaned


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "sku", "quantity", "cost_price",
            "selling_price", "low_stock_threshold", "description",
        ]
        labels = {
            "sku": "SKU",
            "quantity": "Quantity on hand",
            "cost_price": "Cost price",
            "selling_price": "Selling price",
            "low_stock_threshold": "Low stock threshold",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, org, **kwargs):
        super().__init__(*args, **kwargs)
        self.org = org
        self.fields["sku"].help_text = "Must be unique in your organization."
        self.fields["low_stock_threshold"].help_text = (
            f"Leave empty to use your default ({org.default_low_stock_threshold})."
        )

    def clean_sku(self):
        sku = self.cleaned_data["sku"].strip()
        if any(ch.isspace() for ch in sku):
            raise ValidationError("SKU cannot contain spaces.")
        clash = Product.objects.for_org(self.org).filter(sku__iexact=sku)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError(f'A product with SKU "{sku}" already exists in your organization.')
        return sku


class AdjustStockForm(forms.Form):
    delta = forms.IntegerField(label="Units (+/-)", min_value=-1_000_000_000, max_value=1_000_000_000)
    note = forms.CharField(label="Note", max_length=200, required=False)

    def clean_delta(self):
        delta = self.cleaned_data["delta"]
        if delta == 0:
            raise ValidationError("Enter a number other than 0, like 10 or -3.")
        return delta


class SettingsForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["default_low_stock_threshold"]
        labels = {"default_low_stock_threshold": "Default low stock threshold"}
        help_texts = {
            "default_low_stock_threshold": (
                "A product is low on stock when its quantity is at or below its own "
                "threshold. Products without one use this default."
            )
        }
