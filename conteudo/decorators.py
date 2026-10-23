from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def professor_required(view):
    @wraps(view)
    @login_required
    def envolvida(request, *args, **kwargs):
        if request.user.papel != "professor":
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return envolvida