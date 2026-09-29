from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import AuditableViewSet, get_acting_user

from . import filters, models, serializers, services


class ValidSintaxisViewSet(AuditableViewSet):
    """
    CRUD administrativo para la gestión de sintaxis de búsqueda admitidas.
    """
    queryset = models.ValidSintaxis.objects.all()
    serializer_class = serializers.ValidSintaxisSerializer
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]


class LinkCheckLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Consulta de solo lectura del historial de verificaciones de enlaces.
    """
    queryset = models.LinkCheckLog.objects.all()
    serializer_class = serializers.LinkCheckLogSerializer
    filterset_fields = ["platform", "is_active"]
    ordering_fields = ["last_check", "fail_count", "created_at"]


class PlatformViewSet(AuditableViewSet):
    """
    CRUD y ciclo de vida administrativo de plataformas.
    """
    queryset = models.Platform.objects.all()
    serializer_class = serializers.PlatformSerializer
    search_fields = ["name"]
    filterset_fields = [
        "status",
        "requires_registration",
        "has_access_text",
        "valid_sintaxis",
    ]
    ordering_fields = [
        "name",
        "status",
        "start_period",
        "finish_period",
        "created_at",
    ]

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, pk=None):
        instance = self.get_object()
        user = get_acting_user(request)
        updated_platform = services.publish_platform(
            platform=instance,
            user=user,
        )
        return Response(
            self.get_serializer(updated_platform).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="mark-obsolete")
    def mark_obsolete(self, request, pk=None):
        instance = self.get_object()
        user = get_acting_user(request)
        updated_platform = services.mark_platform_obsolete(
            platform=instance,
            user=user,
        )
        return Response(
            self.get_serializer(updated_platform).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="reactivate")
    def reactivate(self, request, pk=None):
        instance = self.get_object()
        user = get_acting_user(request)
        updated_platform = services.reactivate_platform(
            platform=instance,
            user=user,
        )
        return Response(
            self.get_serializer(updated_platform).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="check-link")
    def check_link(self, request, pk=None):
        instance = self.get_object()
        user = get_acting_user(request)
        link_log = services.check_platform_link(
            platform=instance,
            user=user,
        )
        return Response(
            serializers.LinkCheckLogSerializer(link_log).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        model = self.queryset.model
        try:
            instance = model.all_objects.get(pk=pk, deleted_at__isnull=False)
        except (model.DoesNotExist, ValueError):
            return Response(
                {"detail": "No existe un registro eliminado con ese id."},
                status=status.HTTP_404_NOT_FOUND,
            )

        acting_user = get_acting_user(request)
        instance.restore()
        # Regla de negocio: una plataforma restaurada regresa a borrador y requiere nueva validación.
        instance.status = models.Platform.Status.BORRADOR
        instance.validated_by = None
        instance.validated_at = None
        instance.updated_by = acting_user
        instance.updated_at = timezone.now()
        instance.save(
            update_fields=[
                "status",
                "validated_by",
                "validated_at",
                "updated_by",
                "updated_at",
            ]
        )
        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)


class PlatformPublicViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Exploración pública de plataformas publicadas y no eliminadas.
    """
    queryset = models.Platform.objects.filter(
        status=models.Platform.Status.PUBLICADO,
    ).distinct()
    serializer_class = serializers.PlatformPublicSerializer
    filterset_class = filters.PlatformPublicFilter
    search_fields = ["name"]
    ordering_fields = ["name", "start_period", "finish_period"]
