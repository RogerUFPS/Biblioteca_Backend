from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType

from .models import AccessPreset, User


class RequestAuditMiddleware:
    """Registra cada solicitud de API sin guardar sus credenciales ni su cuerpo."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path_info.startswith("/api/"):
            actor = getattr(request, "user", None)
            if not getattr(actor, "is_authenticated", False):
                actor = None
            resolver_match = getattr(request, "resolver_match", None)
            view_class = getattr(
                getattr(resolver_match, "func", None),
                "cls",
                None,
            )
            queryset = getattr(view_class, "queryset", None)
            model = getattr(queryset, "model", None)
            if model is None:
                view_name = getattr(resolver_match, "view_name", "") or ""
                model = AccessPreset if "preset" in view_name else User
            LogEntry.objects.create(
                action=LogEntry.Action.ACCESS,
                content_type=ContentType.objects.get_for_model(model),
                object_pk=str(getattr(resolver_match, "kwargs", {}).get("pk", "")),
                object_repr=f"{request.method} {request.path_info}"[:200],
                actor=actor,
                remote_addr=request.META.get("REMOTE_ADDR"),
                changes={
                    "method": [None, request.method],
                    "path": [None, request.path_info],
                    "status": [None, response.status_code],
                },
                additional_data={"status_code": response.status_code},
            )
        return response
