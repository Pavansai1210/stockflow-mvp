from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import Organization, Product, Profile

EMAIL = "demo@stockflow.test"
PASSWORD = "Password123"

# name, sku, qty, cost, price, threshold (None = organization default of 5)
PRODUCTS = [
    ("Cotton T-Shirt (Black)", "TS-BLK-001", 42, "4.50", "12.00", 10),
    ("Cotton T-Shirt (White)", "TS-WHT-001", 3, "4.50", "12.00", 10),
    ("Canvas Tote Bag", "BAG-TOTE-01", 18, "2.10", "7.50", None),
    ("Ceramic Mug 350ml", "MUG-350", 4, "1.80", "9.00", None),
    ("Steel Water Bottle", "BTL-STL-750", 25, "5.20", "18.00", 8),
    ("Notebook A5 Ruled", "NB-A5-R", 0, "0.90", "3.50", 15),
    ("Gel Pen Blue (12 pack)", "PEN-GEL-B12", 60, "2.40", "6.00", 12),
    ("Desk Lamp LED", "LMP-LED-01", 7, "8.00", "24.00", None),
    ("USB-C Cable 1m", "CBL-USBC-1M", 5, "1.20", "5.00", None),
    ("Wireless Mouse", "MSE-WL-01", 14, "6.50", "19.00", 5),
    ("Laptop Stand", "STD-LAP-01", 2, "11.00", "29.00", 4),
    ("Sticker Pack", "STK-PACK-01", 120, "0.30", "2.00", 30),
]


class Command(BaseCommand):
    help = "Create a demo account with sample products."

    @transaction.atomic
    def handle(self, *args, **options):
        if User.objects.filter(username=EMAIL).exists():
            self.stdout.write(f"Demo user already exists: {EMAIL} / {PASSWORD}")
            return
        org = Organization.objects.create(name="Demo Store")
        user = User.objects.create_user(username=EMAIL, email=EMAIL, password=PASSWORD)
        Profile.objects.create(user=user, organization=org)
        for name, sku, qty, cost, price, threshold in PRODUCTS:
            Product.objects.create(
                organization=org, name=name, sku=sku, quantity=qty,
                cost_price=cost, selling_price=price,
                low_stock_threshold=threshold, last_updated_by=user,
            )
        self.stdout.write(self.style.SUCCESS(f"Seeded demo data. Log in with {EMAIL} / {PASSWORD}"))
