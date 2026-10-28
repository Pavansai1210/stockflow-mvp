from django.contrib import messages
from django.contrib.auth import login, logout
from django.db.models import Count, F, IntegerField, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .decorators import org_required
from .forms import AdjustStockForm, LoginForm, ProductForm, SettingsForm, SignupForm
from .models import Product


# ---------- Authentication ----------

def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignupForm(request.POST) if request.method == "POST" else SignupForm()
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(
            request,
            f"Welcome to StockFlow, {user.profile.organization.name}. "
            "Add your first product to get started.",
        )
        return redirect("dashboard")
    return render(request, "inventory/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = LoginForm(request, request.POST) if request.method == "POST" else LoginForm(request)
    if request.method == "POST" and form.is_valid():
        login(request, form.user)
        next_url = request.GET.get("next", "")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect("dashboard")
    return render(request, "inventory/login.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


# ---------- Dashboard ----------

@org_required
def dashboard(request):
    org = request.org
    totals = Product.objects.for_org(org).aggregate(
        products=Count("id"),
        units=Coalesce(Sum("quantity"), 0, output_field=IntegerField()),
    )
    low = Product.objects.low_stock(org)
    low_items = low.annotate(gap=F("quantity") - F("threshold")).order_by("gap", "name")[:50]
    return render(request, "inventory/dashboard.html", {
        "totals": totals,
        "low_items": low_items,
        "low_count": low.count(),
    })


# ---------- Products ----------

@org_required
def product_list(request):
    q = request.GET.get("q", "").strip()[:100]
    products = Product.objects.for_org(request.org).with_threshold(request.org)
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    return render(request, "inventory/product_list.html", {"products": products, "q": q})


@org_required
def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST, org=request.org)
        if form.is_valid():
            product = form.save(commit=False)
            product.organization = request.org      # never taken from the form
            product.last_updated_by = request.user
            product.save()
            messages.success(request, f"Added {product.name}.")
            return redirect("product_list")
    else:
        form = ProductForm(org=request.org, initial={"quantity": 0})
    return render(request, "inventory/product_form.html", {"form": form, "product": None})


@org_required
def product_edit(request, pk):
    # organization=request.org -> another tenant's product id gives a 404.
    product = get_object_or_404(Product, pk=pk, organization=request.org)
    if request.method == "POST":
        form = ProductForm(request.POST, instance=product, org=request.org)
        if form.is_valid():
            product = form.save(commit=False)
            product.last_updated_by = request.user
            product.save()
            messages.success(request, f"Saved changes to {product.name}.")
            return redirect("product_list")
    else:
        form = ProductForm(instance=product, org=request.org)
    return render(request, "inventory/product_form.html", {
        "form": form, "product": product, "adjust_form": AdjustStockForm(),
    })


@require_POST
@org_required
def product_adjust(request, pk):
    product = get_object_or_404(Product, pk=pk, organization=request.org)
    form = AdjustStockForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
        return redirect("product_edit", pk=product.pk)

    delta = form.cleaned_data["delta"]
    # One atomic UPDATE; the filter guarantees stock never goes below zero.
    updated = (
        Product.objects.for_org(request.org)
        .filter(pk=product.pk, quantity__gte=max(0, -delta))
        .update(
            quantity=F("quantity") + delta,
            last_note=form.cleaned_data["note"],
            last_updated_by=request.user,
            updated_at=timezone.now(),
        )
    )
    if updated:
        sign = "+" if delta > 0 else ""
        messages.success(request, f"Stock updated: {product.name} {sign}{delta}.")
    else:
        messages.error(
            request,
            f"Cannot remove {abs(delta)} units. Only {product.quantity} on hand.",
        )
    return redirect("product_edit", pk=product.pk)


@require_POST
@org_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk, organization=request.org)
    name = product.name
    product.delete()
    messages.success(request, f"Deleted {name}.")
    return redirect("product_list")


# ---------- Settings ----------

@org_required
def settings_view(request):
    if request.method == "POST":
        form = SettingsForm(request.POST, instance=request.org)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved.")
            return redirect("settings")
    else:
        form = SettingsForm(instance=request.org)
    return render(request, "inventory/settings.html", {"form": form})
