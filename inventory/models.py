from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, IntegerField, Value
from django.db.models.functions import Coalesce


class Organization(models.Model):
    """The tenant. All products belong to exactly one organization."""

    name = models.CharField(max_length=80)
    default_low_stock_threshold = models.PositiveIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Profile(models.Model):
    """Links a Django user to their organization (one user per org in the MVP)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="members"
    )

    def __str__(self):
        return f"{self.user} @ {self.organization}"


class ProductQuerySet(models.QuerySet):
    """Helpers that make tenant scoping explicit and hard to forget."""

    def for_org(self, org):
        return self.filter(organization=org)

    def with_threshold(self, org):
        """Adds `threshold`: the product's own value, or the org default if empty."""
        return self.annotate(
            threshold=Coalesce(
                "low_stock_threshold",
                Value(org.default_low_stock_threshold),
                output_field=IntegerField(),
            )
        )

    def low_stock(self, org):
        """Low stock rule: quantity <= threshold."""
        return (
            self.for_org(org)
            .with_threshold(org)
            .filter(quantity__lte=F("threshold"))
        )


class Product(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="products"
    )
    name = models.CharField(max_length=120)
    sku = models.CharField(max_length=64)
    description = models.TextField(blank=True, max_length=1000)
    quantity = models.PositiveIntegerField(default=0)
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    selling_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    low_stock_threshold = models.PositiveIntegerField(null=True, blank=True)
    last_note = models.CharField(max_length=200, blank=True)
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            # SKU must be unique inside one organization (not globally).
            models.UniqueConstraint(
                fields=["organization", "sku"], name="unique_sku_per_org"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"
