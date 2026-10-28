from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def org_required(view):
    """Require login AND attach the user's organization to the request.

    The organization always comes from the logged-in user, never from the URL
    or form data. Every view then filters by `request.org`, which is what keeps
    one tenant's data away from another.
    """

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        profile = getattr(request.user, "profile", None)
        if profile is None:  # e.g. a superuser created without an organization
            logout(request)
            messages.error(request, "This account has no organization. Sign up for a new account.")
            return redirect("login")
        request.org = profile.organization
        return view(request, *args, **kwargs)

    return wrapper
