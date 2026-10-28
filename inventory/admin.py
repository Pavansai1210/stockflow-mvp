from django.contrib import admin

from .models import Organization, Product, Profile

admin.site.register(Organization)
admin.site.register(Profile)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "organization", "quantity", "low_stock_threshold")
    list_filter = ("organization",)
    search_fields = ("name", "sku")
