# StockFlow MVP (Django)

A minimal multi-tenant SaaS inventory app built for the 6-hour MVP brief.
Sign up with an organization, manage products, and watch low-stock items on a dashboard.

**Stack:** Python 3.10+, Django 4.2 / 5.x, SQLite, Django templates, hand-written CSS.

## Run it (Windows)

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations inventory
python manage.py migrate
python manage.py seed_demo          :: optional demo data (demo@stockflow.test / Password123)
python manage.py runserver
```
Open http://127.0.0.1:8000

Mac/Linux: use `source venv/bin/activate` instead of `venv\Scripts\activate`.

Run the automated tests:
```bat
python manage.py test
```

## Feature checklist (maps to the PRD)

| PRD | Delivered |
|---|---|
| FR-1 Signup / login | Email, password, confirm password, organization name. Validation and hashed passwords (Django auth) |
| FR-2 Organization context | Signup creates Organization + User + Profile in one transaction. Every product has `organization` |
| FR-3 Product model | All PRD fields, plus `last_updated_by` and `last_note` |
| FR-4 Product CRUD | Create, list (search by name or SKU), edit, hard delete with confirm dialog |
| FR-5 Stock updates | Edit quantity in the form, plus "Adjust stock" (+/- N units and a note) |
| FR-6 Dashboard | Total products, total units, low-stock count and table |
| FR-7 Settings | Default low stock threshold (default 5) |

Low stock rule: `quantity <= COALESCE(product.low_stock_threshold, organization.default_low_stock_threshold)`,
done in the database with `Coalesce` + `F()` (see `ProductQuerySet.low_stock`).

## Tenant isolation

- The `@org_required` decorator (`inventory/decorators.py`) requires login and sets `request.org` from the logged-in user's `Profile`. The organization is never read from the URL or form data.
- Every product query is scoped with `for_org(request.org)` or `get_object_or_404(Product, pk=pk, organization=request.org)`, so another tenant's product ID returns **404**.
- On create, `organization` is set in the view and is not a form field, so it can't be forged.
- SKU uniqueness is per organization: `UniqueConstraint(organization, sku)`, plus a case-insensitive check in `ProductForm.clean_sku`.
- `TenantIsolationTests` in `inventory/tests.py` proves org B can't see, edit, adjust or delete org A's product.

## Other decisions

- **Django built-ins:** auth (PBKDF2 password hashing), sessions, CSRF protection, messages, ORM (no raw SQL, so no SQL injection), template auto-escaping.
- **Username = email:** users log in with their email, stored in Django's `username` field.
- **Stock adjust:** one atomic `UPDATE ... SET quantity = quantity + N` with a guard so stock never drops below zero (safe under concurrent requests).
- **Hard delete:** allowed by the PRD; POST-only with a confirm dialog.
- **Admin:** models are registered in the Django admin (`python manage.py createsuperuser`).

## Known limits (out of scope per the PRD)

No password reset, roles/invites, stock movement history, CSV import, pagination, or login rate limiting.
Next steps: pagination, a `StockMovement` model for history, and rate limiting on login.

## Structure

```
config/                 project settings and root urls
inventory/
  models.py             Organization, Profile, Product (+ tenant-scoped queryset)
  forms.py              signup, login, product, adjust stock, settings
  views.py              all pages
  decorators.py         @org_required
  urls.py               routes
  admin.py              admin registration
  tests.py              automated tests
  templates/            HTML
  static/inventory/     CSS + confirm-dialog script
  management/commands/seed_demo.py   demo data
```
