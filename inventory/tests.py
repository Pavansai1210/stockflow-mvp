"""End-to-end checks: auth, validation, low-stock logic and tenant isolation.

Run with:  python manage.py test
"""
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Organization, Product, Profile


def make_account(email, org_name="Test Org", password="Password123"):
    """Create org + user + profile directly and return (user, org)."""
    org = Organization.objects.create(name=org_name)
    user = User.objects.create_user(username=email, email=email, password=password)
    Profile.objects.create(user=user, organization=org)
    return user, org


def logged_in_client(user):
    client = Client()
    client.force_login(user)
    return client


def make_product(org, **kwargs):
    defaults = {"name": "Widget", "sku": "W-1", "quantity": 10}
    defaults.update(kwargs)
    return Product.objects.create(organization=org, **defaults)


class AuthTests(TestCase):
    def test_anonymous_users_are_redirected_to_login(self):
        for name in ["dashboard", "product_list", "product_create", "settings"]:
            res = self.client.get(reverse(name))
            self.assertEqual(res.status_code, 302, name)
            self.assertIn(reverse("login"), res["Location"], name)

    def test_signup_creates_org_user_and_logs_in(self):
        res = self.client.post(reverse("signup"), {
            "org_name": "My Test Store", "email": "Owner@Example.com",
            "password": "Password123", "confirm_password": "Password123",
        })
        self.assertRedirects(res, reverse("dashboard"))
        user = User.objects.get(username="owner@example.com")
        self.assertEqual(user.profile.organization.name, "My Test Store")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_signup_validation(self):
        res = self.client.post(reverse("signup"), {
            "org_name": "", "email": "nope", "password": "short", "confirm_password": "x",
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
        self.assertContains(res, "Fix the highlighted fields")

    def test_signup_rejects_duplicate_email(self):
        make_account("dup@example.com")
        res = self.client.post(reverse("signup"), {
            "org_name": "Other", "email": "DUP@example.com",
            "password": "Password123", "confirm_password": "Password123",
        })
        self.assertContains(res, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_login_works_and_rejects_wrong_password(self):
        make_account("login@example.com")
        bad = self.client.post(reverse("login"), {"email": "login@example.com", "password": "wrong-pass"})
        self.assertContains(bad, "Email or password is incorrect.")
        good = self.client.post(reverse("login"), {"email": "login@example.com", "password": "Password123"})
        self.assertRedirects(good, reverse("dashboard"))

    def test_csrf_is_enforced_on_post(self):
        strict = Client(enforce_csrf_checks=True)
        res = strict.post(reverse("login"), {"email": "a@b.co", "password": "x"})
        self.assertEqual(res.status_code, 403)


class ProductTests(TestCase):
    def setUp(self):
        self.user, self.org = make_account("crud@example.com")
        self.client = logged_in_client(self.user)

    def test_create_product_sets_org_from_session(self):
        res = self.client.post(reverse("product_create"), {
            "name": "Pen", "sku": "PEN-1", "quantity": "50", "selling_price": "3",
        })
        self.assertRedirects(res, reverse("product_list"))
        product = Product.objects.get()
        self.assertEqual(product.organization, self.org)
        self.assertEqual(product.last_updated_by, self.user)
        self.assertContains(self.client.get(reverse("product_list")), "Pen")

    def test_required_fields_and_negative_quantity(self):
        res = self.client.post(reverse("product_create"), {"name": "", "sku": "", "quantity": "-4"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_sku_unique_per_org_case_insensitive(self):
        make_product(self.org, sku="W-1")
        res = self.client.post(reverse("product_create"), {"name": "Other", "sku": "w-1", "quantity": "1"})
        self.assertContains(res, "already exists")
        self.assertEqual(Product.objects.count(), 1)

    def test_same_sku_allowed_in_different_orgs(self):
        _, other_org = make_account("other@example.com", "Other Org")
        make_product(other_org, sku="W-1")
        res = self.client.post(reverse("product_create"), {"name": "Mine", "sku": "W-1", "quantity": "1"})
        self.assertRedirects(res, reverse("product_list"))
        self.assertEqual(Product.objects.filter(sku="W-1").count(), 2)

    def test_edit_and_delete(self):
        p = make_product(self.org)
        res = self.client.post(reverse("product_edit", args=[p.pk]), {
            "name": "Renamed", "sku": "W-1", "quantity": "7",
        })
        self.assertRedirects(res, reverse("product_list"))
        p.refresh_from_db()
        self.assertEqual((p.name, p.quantity), ("Renamed", 7))
        res = self.client.post(reverse("product_delete", args=[p.pk]))
        self.assertRedirects(res, reverse("product_list"))
        self.assertFalse(Product.objects.exists())

    def test_delete_requires_post(self):
        p = make_product(self.org)
        self.assertEqual(self.client.get(reverse("product_delete", args=[p.pk])).status_code, 405)
        self.assertTrue(Product.objects.exists())

    def test_search_by_name_or_sku(self):
        make_product(self.org, name="Blue Pen", sku="BP-1")
        make_product(self.org, name="Mug", sku="MUG-1")
        by_name = self.client.get(reverse("product_list"), {"q": "pen"})
        self.assertContains(by_name, "Blue Pen")
        self.assertNotContains(by_name, "MUG-1")
        by_sku = self.client.get(reverse("product_list"), {"q": "mug"})
        self.assertContains(by_sku, "MUG-1")

    def test_adjust_stock(self):
        p = make_product(self.org, quantity=10)
        url = reverse("product_adjust", args=[p.pk])
        self.client.post(url, {"delta": "5", "note": "Restock"})
        p.refresh_from_db()
        self.assertEqual((p.quantity, p.last_note), (15, "Restock"))
        self.client.post(url, {"delta": "-3"})
        p.refresh_from_db()
        self.assertEqual(p.quantity, 12)

    def test_adjust_cannot_go_below_zero(self):
        p = make_product(self.org, quantity=2)
        res = self.client.post(reverse("product_adjust", args=[p.pk]), {"delta": "-9999"}, follow=True)
        p.refresh_from_db()
        self.assertEqual(p.quantity, 2)
        self.assertContains(res, "Cannot remove")


class LowStockTests(TestCase):
    def setUp(self):
        self.user, self.org = make_account("low@example.com")
        self.client = logged_in_client(self.user)

    def test_default_threshold_is_five_and_boundary_is_inclusive(self):
        make_product(self.org, name="Exactly Five", sku="A", quantity=5)
        make_product(self.org, name="Six Units", sku="B", quantity=6)
        res = self.client.get(reverse("dashboard"))
        self.assertEqual(res.context["low_count"], 1)
        self.assertContains(res, "Exactly Five")
        self.assertNotContains(res, "Six Units")

    def test_product_threshold_overrides_default(self):
        make_product(self.org, name="Plenty", sku="P", quantity=50, low_stock_threshold=60)
        make_product(self.org, name="Calm", sku="C", quantity=3, low_stock_threshold=2)
        res = self.client.get(reverse("dashboard"))
        self.assertContains(res, "Plenty")
        self.assertNotContains(res, "Calm")

    def test_dashboard_totals(self):
        make_product(self.org, sku="A", quantity=10)
        make_product(self.org, sku="B", quantity=4)
        totals = self.client.get(reverse("dashboard")).context["totals"]
        self.assertEqual((totals["products"], totals["units"]), (2, 14))

    def test_empty_dashboard_totals_are_zero(self):
        totals = self.client.get(reverse("dashboard")).context["totals"]
        self.assertEqual((totals["products"], totals["units"]), (0, 0))

    def test_changing_default_in_settings_changes_low_stock(self):
        make_product(self.org, name="Gadget", sku="G", quantity=8)
        self.assertNotContains(self.client.get(reverse("dashboard")), "Gadget")
        res = self.client.post(reverse("settings"), {"default_low_stock_threshold": "10"})
        self.assertRedirects(res, reverse("settings"))
        self.assertContains(self.client.get(reverse("dashboard")), "Gadget")

    def test_settings_rejects_negative_value(self):
        res = self.client.post(reverse("settings"), {"default_low_stock_threshold": "-1"})
        self.assertEqual(res.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.default_low_stock_threshold, 5)


class TenantIsolationTests(TestCase):
    """Organization B must never see or change organization A's data."""

    def setUp(self):
        self.user_a, self.org_a = make_account("a@example.com", "Org A")
        self.user_b, self.org_b = make_account("b@example.com", "Org B")
        self.product_a = make_product(self.org_a, name="Secret Widget", sku="SEC-1", quantity=9)
        self.client_b = logged_in_client(self.user_b)

    def test_lists_search_and_dashboard_hide_other_orgs_products(self):
        self.assertNotContains(self.client_b.get(reverse("product_list")), "Secret Widget")
        self.assertNotContains(self.client_b.get(reverse("product_list"), {"q": "SEC"}), "Secret Widget")
        self.assertNotContains(self.client_b.get(reverse("dashboard")), "Secret Widget")
        totals = self.client_b.get(reverse("dashboard")).context["totals"]
        self.assertEqual(totals["products"], 0)

    def test_cannot_view_edit_adjust_or_delete_other_orgs_product(self):
        pk = self.product_a.pk
        self.assertEqual(self.client_b.get(reverse("product_edit", args=[pk])).status_code, 404)
        self.assertEqual(self.client_b.post(reverse("product_edit", args=[pk]), {
            "name": "Hacked", "sku": "SEC-1", "quantity": "0"}).status_code, 404)
        self.assertEqual(self.client_b.post(reverse("product_adjust", args=[pk]), {"delta": "-5"}).status_code, 404)
        self.assertEqual(self.client_b.post(reverse("product_delete", args=[pk])).status_code, 404)

        self.product_a.refresh_from_db()
        self.assertEqual((self.product_a.name, self.product_a.quantity), ("Secret Widget", 9))

    def test_owner_still_has_access(self):
        client_a = logged_in_client(self.user_a)
        res = client_a.get(reverse("product_edit", args=[self.product_a.pk]))
        self.assertContains(res, "Secret Widget")

    def test_settings_only_change_own_org(self):
        self.client_b.post(reverse("settings"), {"default_low_stock_threshold": "99"})
        self.org_a.refresh_from_db()
        self.org_b.refresh_from_db()
        self.assertEqual(self.org_a.default_low_stock_threshold, 5)
        self.assertEqual(self.org_b.default_low_stock_threshold, 99)
